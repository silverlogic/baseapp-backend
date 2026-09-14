from __future__ import annotations

import swapper
from django.apps import apps
from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import SharedServiceProvider


class OrganizationAccountService(SharedServiceProvider):
    """
    Exposes organization-ownership checks to other packages (e.g. baseapp_auth)
    without a direct import of baseapp_organizations.

    Registered in `apps.py` via `register_shared_services` under the name
    `organizations.account`. Consumers resolve it lazily through
    `shared_services.get("organizations.account")`, so the behaviour is opt-in
    and degrades gracefully when this package is not installed.
    """

    @property
    def service_name(self) -> str:
        return "organizations.account"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_organizations")

    def user_owns_organization(self, user) -> bool:
        """Return `True` if `user` owns at least one organization (via its profile)."""
        Organization = swapper.load_model("baseapp_organizations", "Organization")
        return Organization.objects.filter(profile__owner_id=user.id).exists()

    def get_account_deletion_block_reason(self, user) -> str | None:
        """
        Return why user's account cannot be deleted, or `None` if it can.

        An organization owner must transfer ownership or delete the organization
        before their account can be removed.
        """
        if self.user_owns_organization(user):
            return _(
                "Account cannot be deleted because you're the owner of an organization. Transfer ownership or delete the organization first."
            )
        return None
