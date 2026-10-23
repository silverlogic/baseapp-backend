"""
Impersonation sessions: starting and ending them, validating the tokens they issue, and
recording the writes made during them.

Tokens of a session carry two extra claims, `imp` (the impersonator's pk) and `imp_sid`
(the session's pk). Every request authenticated with such a token is checked against the
session, so ending a session revokes its tokens at once, whatever their `exp`.
"""

import logging
import re
from contextvars import ContextVar
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import datetime_to_epoch

from . import conf
from .exceptions import (
    ImpersonationForbidden,
    ImpersonationNotAllowed,
    ImpersonationReadOnly,
    ImpersonationSessionInvalid,
)
from .models import ImpersonationAction, ImpersonationSession
from .signals import (
    impersonation_action,
    impersonation_denied,
    impersonation_ended,
    impersonation_started,
)
from .tokens import ImpersonationRefreshToken

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

IMPERSONATOR_CLAIM = "imp"
SESSION_CLAIM = "imp_sid"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Mutations that manage the session itself. They are always allowed and are not recorded
# as actions; starting and ending are recorded on the session row.
SESSION_MUTATIONS = frozenset({"impersonationEnd"})

MAX_REASON_LENGTH = 2000

# The session of the request being served, set by ImpersonationMiddleware for the length
# of the request. Lets code that only has the user (permission backends) find it.
_current_session: ContextVar["ImpersonationSession | None"] = ContextVar(
    "baseapp_impersonation_session", default=None
)


# Sessions


def _cache_key(session_id: Any) -> str:
    return f"baseapp_impersonation:session:{session_id}"


def get_session(session_id: Any) -> "ImpersonationSession | None":
    """The session with this pk, cached for `BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT`."""
    key = _cache_key(session_id)
    session = cache.get(key)
    if session is None:
        session = (
            ImpersonationSession.objects.select_related("impersonator", "target")
            .filter(pk=session_id)
            .first()
        )
        if session is None:
            return None
        cache.set(key, session, conf.get_cache_timeout())
    return session


def invalidate_session_cache(session_id: Any) -> None:
    cache.delete(_cache_key(session_id))


def can_impersonate(
    impersonator: "AbstractBaseUser",
    target: "AbstractBaseUser",
    request: "HttpRequest | None" = None,
) -> bool:
    """
    Whether `impersonator` may start a session as `target`.

    Some rules hold whatever the project says: both users are active, they are different
    people, and nobody starts a session from inside another one. The rest is decided by the
    `BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE` hook.
    """
    if not getattr(impersonator, "is_authenticated", False):
        return False
    if not impersonator.is_active or not target.is_active or impersonator.pk == target.pk:
        return False
    if request is not None and get_impersonation(request) is not None:
        return False
    return bool(conf.get_can_impersonate()(impersonator, target, request))


def start_impersonation(
    impersonator: "AbstractBaseUser",
    target: "AbstractBaseUser",
    reason: str,
    *,
    request: "HttpRequest | None" = None,
) -> tuple[ImpersonationSession, ImpersonationRefreshToken]:
    """
    Open a session and issue its refresh token. The access token is `refresh.access_token`.

    Raises `ValidationError` for a missing reason and `ImpersonationNotAllowed` when the
    rules refuse the pair; a refusal also sends `impersonation_denied`.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError(_("A reason is required."), code="required")
    if len(reason) > MAX_REASON_LENGTH:
        raise ValidationError(
            _("The reason must be at most %(max)s characters."),
            code="max_length",
            params={"max": MAX_REASON_LENGTH},
        )

    if not can_impersonate(impersonator, target, request):
        impersonation_denied.send(
            sender=ImpersonationSession,
            impersonator=impersonator,
            target=target,
            request=request,
        )
        raise ImpersonationNotAllowed()

    now = timezone.now()
    session = ImpersonationSession.objects.create(
        impersonator=impersonator,
        target=target,
        reason=reason,
        read_only=conf.is_read_only(),
        started_at=now,
        expires_at=now + conf.get_ttl(),
        ip=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request is not None else "",
    )
    refresh = issue_refresh_token(session)
    impersonation_started.send(sender=ImpersonationSession, session=session, request=request)
    return session, refresh


def issue_refresh_token(session: ImpersonationSession) -> ImpersonationRefreshToken:
    """
    A refresh token for the session's target, with the same claims a login would give.

    The token is built by the project's `TOKEN_OBTAIN_SERIALIZER`, so custom claims match an
    ordinary login. Its `exp` is capped at the session's expiry, and the project's
    `BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK` may add claims last.
    """
    obtain_serializer = import_string(api_settings.TOKEN_OBTAIN_SERIALIZER)
    base = obtain_serializer.get_token(session.target)

    refresh = ImpersonationRefreshToken()
    refresh.payload = dict(base.payload)
    refresh[IMPERSONATOR_CLAIM] = session.impersonator_id
    refresh[SESSION_CLAIM] = session.pk
    refresh["exp"] = min(refresh["exp"], datetime_to_epoch(session.expires_at))

    if hook := conf.get_token_hook():
        hook(refresh, session.target, session.impersonator)
    return refresh


def end_impersonation(
    session: ImpersonationSession,
    reason: str = ImpersonationSession.EndReason.ENDED,
    *,
    request: "HttpRequest | None" = None,
) -> bool:
    """End a session. Returns False when it had already ended; nothing is sent then."""
    now = timezone.now()
    if session.expires_at <= now:
        reason = ImpersonationSession.EndReason.EXPIRED
        now = session.expires_at
    return _close(session, now, reason, request)


def _close(
    session: ImpersonationSession,
    ended_at: datetime,
    reason: str,
    request: "HttpRequest | None",
) -> bool:
    updated = ImpersonationSession.objects.filter(pk=session.pk, ended_at__isnull=True).update(
        ended_at=ended_at, end_reason=reason
    )
    invalidate_session_cache(session.pk)
    if not updated:
        return False
    session.ended_at = ended_at
    session.end_reason = reason
    impersonation_ended.send(
        sender=ImpersonationSession, session=session, reason=reason, request=request
    )
    return True


# Tokens


def validate_session_token(token: Any) -> "ImpersonationSession | None":
    """
    The session a token belongs to, or None for an ordinary token.

    Raises `ImpersonationSessionInvalid` (a 401) when the session has ended or expired, its
    impersonator was deactivated, or the token's claims do not match it. A session found
    expired is closed on the way.
    """
    session_id = token.get(SESSION_CLAIM)
    if session_id is None:
        return None

    session = get_session(session_id)
    if session is None:
        raise ImpersonationSessionInvalid()

    target_id = getattr(session.target, api_settings.USER_ID_FIELD)
    if str(token.get(IMPERSONATOR_CLAIM)) != str(session.impersonator_id) or str(
        token.get(api_settings.USER_ID_CLAIM)
    ) != str(target_id):
        raise ImpersonationSessionInvalid()

    if session.ended_at is not None:
        raise ImpersonationSessionInvalid()
    if session.expires_at <= timezone.now():
        _close(session, session.expires_at, ImpersonationSession.EndReason.EXPIRED, None)
        raise ImpersonationSessionInvalid()
    if not session.impersonator.is_active:
        _close(session, timezone.now(), ImpersonationSession.EndReason.REVOKED, None)
        raise ImpersonationSessionInvalid()
    return session


def check_impersonation(
    request_or_scope: Any, token: Any, *, enforce_read_only: bool = True
) -> "ImpersonationSession | None":
    """
    Validate a request's (or an ASGI scope's) token against its session and attach the
    session as `request.impersonation` (`scope["impersonation"]`).

    For an HTTP request outside GraphQL it also applies `enforce_read_only_request` (403s for
    denylisted writes, and for any write in a read-only session unless allowlisted). GraphQL
    requests are left to `ImpersonationReadOnlyMiddleware`, which can tell queries from
    mutations.

    Call this from any custom JWT authentication; `ImpersonationJWTAuthenticationMixin` and
    `ImpersonationMiddleware` already do.
    """
    attached = get_impersonation(request_or_scope)
    if attached is not None and str(attached.pk) == str(token.get(SESSION_CLAIM)):
        session = attached
    else:
        session = validate_session_token(token)
    if session is None:
        return None

    attach_session(request_or_scope, session)
    if (
        enforce_read_only
        and not isinstance(request_or_scope, dict)
        and not is_graphql_request(request_or_scope)
    ):
        enforce_read_only_request(request_or_scope, session)
    return session


def attach_session(request_or_scope: Any, session: ImpersonationSession) -> None:
    if isinstance(request_or_scope, dict):
        request_or_scope["impersonation"] = session
        if (user := request_or_scope.get("user")) is not None:
            user.impersonation = session
        return
    request_or_scope.impersonation = session
    # A DRF Request wraps the HttpRequest that Django middleware sees.
    if (inner := getattr(request_or_scope, "_request", None)) is not None:
        inner.impersonation = session


def get_impersonation(obj: Any = None) -> "ImpersonationSession | None":
    """
    The active session for a request, a GraphQL context, an ASGI scope or a user.

    With no argument, returns the session of the request being served (set by
    `ImpersonationMiddleware`). For a user, it also falls back to that session when the
    user is its target, so permission backends see it even where no code set
    `user.impersonation`.
    """
    if obj is None:
        return _current_session.get()
    if isinstance(obj, dict):
        session = obj.get("impersonation")
        return session if isinstance(session, ImpersonationSession) else None

    session = getattr(obj, "impersonation", None)
    if isinstance(session, ImpersonationSession):
        return session

    if getattr(obj, "is_authenticated", False) is True and hasattr(obj, "pk"):
        current = _current_session.get()
        if current is not None and current.target_id == obj.pk:
            return current
    return None


def is_impersonated(obj: Any = None) -> bool:
    return get_impersonation(obj) is not None


# Read-only mode


def _split(entries: tuple[str, ...]) -> tuple[list["re.Pattern"], frozenset[str]]:
    """Path regexes (entries starting with "/" or "^") and GraphQL mutation names."""
    paths, mutations = [], set()
    for entry in entries:
        if entry.startswith(("/", "^")):
            paths.append(re.compile(entry))
        else:
            mutations.add(entry)
    return paths, frozenset(mutations)


def _path_matches(entries: tuple[str, ...], path: str) -> bool:
    paths, _mutations = _split(entries)
    return any(pattern.match(path) for pattern in paths)


def is_path_allowlisted(path: str) -> bool:
    return _path_matches(conf.get_read_only_allowlist(), path)


def is_path_denylisted(path: str) -> bool:
    return _path_matches(conf.get_denylist(), path)


def get_mutation_refusal(
    session: ImpersonationSession, name: str
) -> "type[ImpersonationForbidden] | type[ImpersonationReadOnly] | None":
    """Why a GraphQL root mutation may not run during this session, or None if it may."""
    if name in SESSION_MUTATIONS:
        return None
    if name in _split(conf.get_denylist())[1]:
        return ImpersonationForbidden
    if session.read_only and name not in _split(conf.get_read_only_allowlist())[1]:
        return ImpersonationReadOnly
    return None


def is_mutation_allowed(session: ImpersonationSession, name: str) -> bool:
    """Whether a GraphQL root mutation may run during this session."""
    return get_mutation_refusal(session, name) is None


def enforce_read_only_request(request: Any, session: ImpersonationSession) -> None:
    """
    Refuse an unsafe HTTP method on a denylisted path (`ImpersonationForbidden`), or in a
    read-only session on any path not allowlisted (`ImpersonationReadOnly`).
    """
    if request.method in SAFE_METHODS:
        return
    if is_path_denylisted(request.path):
        raise ImpersonationForbidden()
    if session.read_only and not is_path_allowlisted(request.path):
        raise ImpersonationReadOnly()


def is_graphql_view(view_func: Any) -> bool:
    try:
        from graphene_django.views import GraphQLView
    except ImportError:  # pragma: no cover - graphene is optional
        return False
    view_class = getattr(view_func, "view_class", None)
    return isinstance(view_class, type) and issubclass(view_class, GraphQLView)


def is_graphql_request(request: Any) -> bool:
    inner = getattr(request, "_request", request)
    flagged = getattr(inner, "_impersonation_graphql", None)
    if flagged is not None:
        return flagged
    match = getattr(inner, "resolver_match", None)
    return bool(match) and is_graphql_view(match.func)


# Audit


def record_action(
    session: ImpersonationSession,
    *,
    method: str,
    path: str,
    operation_name: str = "",
    status_code: int | None = None,
    request: Any = None,
) -> ImpersonationAction:
    """Record a write made during a session and send `impersonation_action`."""
    action = ImpersonationAction.objects.create(
        session=session,
        method=method,
        path=path,
        operation_name=operation_name,
        status_code=status_code,
    )
    impersonation_action.send(
        sender=ImpersonationAction, action=action, session=session, request=request
    )
    return action


def defer_or_record_action(request: Any, session: ImpersonationSession, **fields: Any) -> None:
    """
    Record a write after the response when `ImpersonationMiddleware` serves the request,
    outside any transaction the write runs in; record it now otherwise.
    """
    pending = getattr(request, "_impersonation_pending_actions", None)
    if pending is None:
        record_action(session, request=request, **fields)
    else:
        pending.append(fields)


def _get_client_ip(request: "HttpRequest | None") -> str | None:
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None
