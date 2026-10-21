from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from trench.utils import get_mfa_model

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

DEFAULT_MFA_POLICY = "baseapp_auth.rest_framework.mfa.policy.MFAPolicy"


class MFAPolicy:
    """
    Decides which MFA changes a user may make. The MFA views ask the policy configured in the
    `BASEAPP_AUTH_MFA_POLICY` setting (a dotted path to a subclass of this class).

    The default allows everything, as the views always did. Subclasses usually only override
    `is_required`: once MFA is required for a user, the default `can_deactivate` refuses to remove
    their last active method and the deactivate view asks for a code even when trench's
    `CONFIRM_DISABLE_WITH_CODE` is off.
    """

    last_method_message = _(
        "Multi-factor authentication is required for your account. "
        "Add another method before removing this one."
    )

    def is_required(self, user: "AbstractBaseUser") -> bool:
        """Whether the user must keep at least one active MFA method."""
        return False

    def can_deactivate(self, user: "AbstractBaseUser", method: str) -> tuple[bool, str | None]:
        """Return `(allowed, reason)`; `reason` is shown to the user when `allowed` is False."""
        if not self.is_required(user):
            return True, None
        active_methods = set(
            get_mfa_model()
            .objects.filter(user_id=user.pk, is_active=True)
            .values_list("name", flat=True)
        )
        if active_methods == {method}:
            return False, str(self.last_method_message)
        return True, None

    def can_change_primary(self, user: "AbstractBaseUser", method: str) -> tuple[bool, str | None]:
        """Return `(allowed, reason)` for making `method` the user's primary method."""
        return True, None


def get_mfa_policy() -> MFAPolicy:
    """Return an instance of the policy class named by `BASEAPP_AUTH_MFA_POLICY`."""
    policy_class = getattr(settings, "BASEAPP_AUTH_MFA_POLICY", DEFAULT_MFA_POLICY)
    if isinstance(policy_class, str):
        policy_class = import_string(policy_class)
    return policy_class()
