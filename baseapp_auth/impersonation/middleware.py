from typing import Any, Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .exceptions import (
    ImpersonationForbidden,
    ImpersonationReadOnly,
    ImpersonationSessionInvalid,
)
from .models import ImpersonationSession
from .services import (
    SAFE_METHODS,
    _current_session,
    check_impersonation,
    enforce_read_only_request,
    is_graphql_view,
    is_token_view,
    record_action,
)


def _error_response(exc: APIException) -> JsonResponse:
    return JsonResponse(exc.detail, status=exc.status_code)


class ImpersonationMiddleware:
    """
    Applies impersonation sessions to every HTTP request, whatever authenticates it.

    - A Bearer token of an ended or expired session gets a 401 with code
      `impersonation_ended`.
    - Unsafe REST requests on the denylist get a 403 with code `impersonation_forbidden`; in
      a read-only session the others get a 403 with code `impersonation_read_only`, unless
      allowlisted. GraphQL is left to
      `ImpersonationReadOnlyMiddleware`, which can tell queries from mutations.
    - SimpleJWT's refresh, verify and blacklist (logout) views are always allowed and never
      recorded, so a client that sends its Bearer header with them keeps working.
    - Every unsafe REST request that runs is recorded as an `ImpersonationAction`, with its
      response status, and so are the mutations `ImpersonationReadOnlyMiddleware` collects.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            session = self._get_session(request)
        except ImpersonationSessionInvalid as exc:
            return _error_response(exc)

        if session is None:
            return self.get_response(request)

        request._impersonation_pending_actions = []
        context_token = _current_session.set(session)
        try:
            response = self.get_response(request)
        finally:
            _current_session.reset(context_token)

        # Written after the response, outside the request's transaction, so writes that
        # failed or rolled back are recorded too.
        for fields in request._impersonation_pending_actions:
            record_action(session, request=request, **fields)
        self._record(request, session, response)
        return response

    def process_view(
        self, request: HttpRequest, view_func: Callable, view_args: Any, view_kwargs: Any
    ) -> HttpResponse | None:
        session = getattr(request, "impersonation", None)
        if session is None:
            return None
        request._impersonation_graphql = is_graphql_view(view_func)
        request._impersonation_token_request = is_token_view(view_func, request.method)
        if request._impersonation_graphql or request._impersonation_token_request:
            return None
        try:
            enforce_read_only_request(request, session)
        except (ImpersonationForbidden, ImpersonationReadOnly) as exc:
            request._impersonation_refused = True
            return _error_response(exc)
        return None

    @staticmethod
    def _get_session(request: HttpRequest) -> ImpersonationSession | None:
        auth = JWTAuthentication()
        header = auth.get_header(request)
        if header is None:
            return None
        raw_token = auth.get_raw_token(header)
        if raw_token is None:
            return None
        try:
            token = auth.get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            # Not ours to reject: the authentication class answers for a bad token.
            return None
        return check_impersonation(request, token, enforce_read_only=False)

    @staticmethod
    def _record(
        request: HttpRequest, session: ImpersonationSession, response: HttpResponse
    ) -> None:
        if request.method in SAFE_METHODS:
            return
        if getattr(request, "_impersonation_graphql", False):
            return
        if getattr(request, "_impersonation_refused", False):
            return
        if getattr(request, "_impersonation_token_request", False):
            return
        record_action(
            session,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            succeeded=response.status_code < 400,
            request=request,
        )
