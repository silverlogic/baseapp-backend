from typing import Any, Callable, Optional

import swapper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.http import HttpResponse
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from baseapp_profiles.rest_framework import CurrentProfileMixin

from .registry import UserType, protected_files
from .services import get_protected_object, serve_protected_file
from .tickets import ProtectedDownloadTicket

Profile = swapper.load_model("baseapp_profiles", "Profile")

INVALID_LINK = _("Invalid download link.")
EXPIRED_LINK = _("This download link has expired.")
STALE_LINK = _("This download link is no longer valid.")


class ProtectedDownloadThrottle(SimpleRateThrottle):
    """
    Per-IP limit on download links, at the DRF rate named ``protected_download``
    (``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]``). No rate configured: no limit.
    """

    scope = "protected_download"

    def get_rate(self) -> Optional[str]:
        return (api_settings.DEFAULT_THROTTLE_RATES or {}).get(self.scope)

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class ProtectedFileDownloadView(CurrentProfileMixin, APIView):
    """
    ``GET {prefix}/{key}/{object_id}``: the file of a registered field, for a caller
    authenticated by the project's DRF authentication (plus the session, so admin links
    work). Access is checked on every request, as the profile the caller acts as.
    """

    permission_classes = [AllowAny]  # access is decided by the registered spec

    def get_authenticators(self) -> list[BaseAuthentication]:
        authenticators = super().get_authenticators()
        if not any(isinstance(auth, SessionAuthentication) for auth in authenticators):
            authenticators.append(SessionAuthentication())
        return authenticators

    def get(self, request: Request, key: str, object_id: str) -> HttpResponse:
        spec = protected_files.get(key)
        if spec is None:
            raise NotFound(_("File not found."))
        obj = get_protected_object(spec, request.user, object_id)
        return serve_protected_file(spec, obj, request, request.user, via="session")


def get_ticket_user_check() -> Optional[Callable[[UserType, Request], bool]]:
    """``BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK``: a callable or its dotted path."""
    check = getattr(settings, "BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK", None)
    if isinstance(check, str):
        check = import_string(check)
    return check


class ProtectedFileTicketView(APIView):
    """
    ``GET {prefix}/t/{ticket}``: the file a download link names. The ticket is the only
    credential, so the link opens natively (a new tab, a download) without headers; it is
    bound to the user who minted it, whose access is checked again on every use.
    """

    authentication_classes: list[type[BaseAuthentication]] = []
    permission_classes = [AllowAny]
    throttle_classes = [ProtectedDownloadThrottle]

    def get(self, request: Request, ticket: str) -> HttpResponse:
        try:
            payload = ProtectedDownloadTicket.load(ticket)
        except signing.SignatureExpired:
            raise PermissionDenied(EXPIRED_LINK) from None
        except signing.BadSignature:
            raise PermissionDenied(INVALID_LINK) from None

        spec = protected_files.get(payload.get("k"))
        if spec is None:
            raise PermissionDenied(INVALID_LINK)

        user = self.get_ticket_user(payload)
        request.user = user
        check = get_ticket_user_check()
        if check is not None and not check(user, request):
            raise PermissionDenied(STALE_LINK)

        obj = get_protected_object(spec, user, payload.get("o"))
        # A file replaced since the link was minted is not the one it was minted for.
        if (spec.get_field_file(obj).name or "") != payload.get("n", ""):
            raise PermissionDenied(STALE_LINK)
        return serve_protected_file(spec, obj, request, user, via="ticket")

    def get_ticket_user(self, payload: dict[str, Any]) -> UserType:
        """
        The user the ticket was minted for, acting as the profile they used then, while they
        may still use it.

        Raises:
            PermissionDenied: the user is gone or inactive, or changed their password.
        """
        if payload.get("u") is None:
            user = AnonymousUser()
        else:
            user = get_user_model()._default_manager.filter(pk=payload["u"]).first()
            if user is None or not user.is_active:
                raise PermissionDenied(STALE_LINK)
        if not ProtectedDownloadTicket.auth_matches(payload, user):
            raise PermissionDenied(STALE_LINK)

        user.current_profile = None
        profile_pk = payload.get("p")
        if profile_pk is not None and user.is_authenticated:
            profile = Profile.objects.filter(pk=profile_pk).first()
            if profile is not None and user.has_perm(
                f"{Profile._meta.app_label}.use_profile", profile
            ):
                user.current_profile = profile
        return user
