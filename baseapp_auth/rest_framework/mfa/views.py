"""
django-trench's MFA views, extended to send the signals in `.signals` and to ask the policy in
`.policy` before a method is deactivated or made primary.

`baseapp_auth.rest_framework.urls.mfa` builds its URLs from `get_mfa_view_class`, so a project can
replace any view through the `BASEAPP_AUTH_MFA_VIEWS` setting instead of copying the URL list.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField
from rest_framework.request import Request
from rest_framework.response import Response
from trench import views as trench_views
from trench.command.deactivate_mfa_method import deactivate_mfa_method_command
from trench.command.set_primary_mfa_method import set_primary_mfa_method_command
from trench.exceptions import MFAValidationError
from trench.responses import ErrorResponse
from trench.serializers import (
    ChangePrimaryMethodCodeValidator,
    ChangePrimaryMethodValidator,
    MFAMethodDeactivationValidator,
)
from trench.utils import get_mfa_model

from .policy import get_mfa_policy
from .signals import (
    mfa_backup_codes_regenerated,
    mfa_method_activated,
    mfa_method_deactivated,
    mfa_primary_method_changed,
)


class RequiredCodeDeactivationValidator(MFAMethodDeactivationValidator):
    """trench's deactivation body with `code` always required."""

    code = CharField(required=True)


def check_policy(result: tuple[bool, str | None]) -> None:
    """Raise a 400 with the policy's reason when it refused the change."""
    allowed, reason = result
    if not allowed:
        raise ValidationError({"non_field_errors": [reason or _("This change is not allowed.")]})


class MFAMethodConfirmActivationView(trench_views.MFAMethodConfirmActivationView):
    """Sends `mfa_method_activated` once the activation code is accepted."""

    def post(self, request: Request, method: str) -> Response:
        response = super().post(request, method)
        if response.status_code == status.HTTP_200_OK:
            mfa_method_activated.send(
                sender=self.__class__, user=request.user, method=method, request=request
            )
        return response


class MFAMethodDeactivationView(trench_views.MFAMethodDeactivationView):
    """
    Asks the MFA policy before deactivating. When the policy says MFA is required for the user, a
    code of the method (or a backup code) is required regardless of `CONFIRM_DISABLE_WITH_CODE`.
    Sends `mfa_method_deactivated` on success.
    """

    def get_validator_class(self, code_required: bool) -> type[MFAMethodDeactivationValidator]:
        if code_required:
            return RequiredCodeDeactivationValidator
        return MFAMethodDeactivationValidator

    def post(self, request: Request, method: str) -> Response:
        user = request.user
        policy = get_mfa_policy()
        # Checked before the code so a refused request doesn't use up a backup code.
        check_policy(policy.can_deactivate(user, method))

        validator_class = self.get_validator_class(code_required=policy.is_required(user))
        serializer = validator_class(mfa_method_name=method, user=user, data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)
        try:
            deactivate_mfa_method_command(mfa_method_name=method, user_id=user.id)
        except MFAValidationError as cause:
            return ErrorResponse(error=cause)

        mfa_method_deactivated.send(
            sender=self.__class__, user=user, method=method, request=request
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MFAMethodBackupCodesRegenerationView(trench_views.MFAMethodBackupCodesRegenerationView):
    """Sends `mfa_backup_codes_regenerated` once new codes are issued."""

    def post(self, request: Request, method: str) -> Response:
        response = super().post(request, method)
        if response.status_code == status.HTTP_200_OK:
            mfa_backup_codes_regenerated.send(
                sender=self.__class__, user=request.user, method=method, request=request
            )
        return response


class MFAPrimaryMethodChangeView(trench_views.MFAPrimaryMethodChangeView):
    """Asks the MFA policy before changing the primary method; sends `mfa_primary_method_changed`."""

    def post(self, request: Request) -> Response:
        user = request.user
        method_serializer = ChangePrimaryMethodValidator(data=request.data)
        method_serializer.is_valid(raise_exception=True)
        method = method_serializer.validated_data["method"]
        check_policy(get_mfa_policy().can_change_primary(user, method))

        code_serializer = ChangePrimaryMethodCodeValidator(
            user=user, mfa_method_name=method, data=request.data
        )
        code_serializer.is_valid(raise_exception=True)

        previous_method = (
            get_mfa_model()
            .objects.filter(user_id=user.id, is_primary=True)
            .values_list("name", flat=True)
            .first()
        )
        try:
            set_primary_mfa_method_command(user_id=user.id, name=method)
        except MFAValidationError as cause:
            return ErrorResponse(error=cause)

        mfa_primary_method_changed.send(
            sender=self.__class__,
            user=user,
            method=method,
            previous_method=previous_method,
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# The views behind each MFA URL, keyed by the names `BASEAPP_AUTH_MFA_VIEWS` accepts.
DEFAULT_MFA_VIEWS = {
    "activate": trench_views.MFAMethodActivationView,
    "activate_confirm": MFAMethodConfirmActivationView,
    "deactivate": MFAMethodDeactivationView,
    "regenerate_codes": MFAMethodBackupCodesRegenerationView,
    "request_code": trench_views.MFAMethodRequestCodeView,
    "config": trench_views.MFAConfigView,
    "user_active_methods": trench_views.MFAListActiveUserMethodsView,
    "change_primary_method": MFAPrimaryMethodChangeView,
}


def get_mfa_view_class(name: str) -> type:
    """
    Return the view class for one of the `DEFAULT_MFA_VIEWS` keys, honouring the project's
    `BASEAPP_AUTH_MFA_VIEWS` setting (a dict of key -> view class or dotted path).
    """
    overrides = getattr(settings, "BASEAPP_AUTH_MFA_VIEWS", None) or {}
    unknown = set(overrides) - set(DEFAULT_MFA_VIEWS)
    if unknown:
        raise ImproperlyConfigured(
            "BASEAPP_AUTH_MFA_VIEWS has unknown keys %s; expected some of %s."
            % (sorted(unknown), sorted(DEFAULT_MFA_VIEWS))
        )
    if name not in DEFAULT_MFA_VIEWS:
        raise KeyError(name)
    view_class = overrides.get(name, DEFAULT_MFA_VIEWS[name])
    if isinstance(view_class, str):
        view_class = import_string(view_class)
    return view_class
