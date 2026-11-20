from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException, AuthenticationFailed


class ImpersonationNotAllowed(Exception):
    """The impersonator may not start a session as this target."""


class CodedDetailMixin:
    """Puts the error code in the response body next to the message, so clients can tell
    these refusals from ordinary authentication and permission errors."""

    default_detail: str
    default_code: str

    def __init__(self, detail=None) -> None:
        super().__init__({"detail": detail or self.default_detail, "code": self.default_code})

    @property
    def message(self) -> str:
        return str(self.detail["detail"])


class ImpersonationSessionInvalid(CodedDetailMixin, AuthenticationFailed):
    """The token belongs to a session that has ended, expired or no longer matches."""

    default_detail = _("The impersonation session has ended.")
    default_code = "impersonation_ended"


class ImpersonationReadOnly(CodedDetailMixin, APIException):
    """A write was attempted during a read-only session."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("This action is not allowed while viewing as another user.")
    default_code = "impersonation_read_only"


class ImpersonationForbidden(CodedDetailMixin, APIException):
    """A write on the denylist was attempted during a session, in either mode."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("This action is never allowed while acting as another user.")
    default_code = "impersonation_forbidden"
