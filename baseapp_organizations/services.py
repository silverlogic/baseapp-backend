from __future__ import annotations

from typing import TYPE_CHECKING

import swapper
from django.apps import apps
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import SharedServiceProvider

if TYPE_CHECKING:
    from baseapp_profiles.models import AbstractProfile


class OrganizationService:
    """
    Create organizations — and their profiles — outside GraphQL: in the admin, data
    migrations, importers or management commands.

    `organizationCreate` makes the signed-in user the profile's owner. Here the owner is
    optional: an organization created without one is run by its ADMIN members, and the
    profiles package keeps such a profile from ever losing its last admin.
    """

    @classmethod
    def create(
        cls,
        name: str,
        *,
        owner: AbstractBaseUser | None = None,
        url_path: str | None = None,
        **fields,
    ) -> models.Model:
        """
        Create an organization named `name` and link a new profile to it.

        `url_path` sets the profile's handle (collisions get a numeric suffix); without it
        the handle is derived from the name. Extra `fields` go to the organization model.
        """
        Organization = swapper.load_model("baseapp_organizations", "Organization")
        with transaction.atomic():
            organization = Organization.objects.create(name=name, **fields)
            cls.ensure_profile(organization, owner=owner, url_path=url_path)
        return organization

    @classmethod
    def ensure_profile(
        cls,
        organization: models.Model,
        *,
        owner: AbstractBaseUser | None = None,
        url_path: str | None = None,
    ) -> "AbstractProfile":
        """Return the organization's profile, creating and linking one if it has none."""
        if organization.profile_id:
            return organization.profile

        Profile = swapper.load_model("baseapp_profiles", "Profile")
        with transaction.atomic():
            profile = Profile.objects.create(
                owner=owner,
                name=organization.name,
                target_content_type=ContentType.objects.get_for_model(organization),
                target_object_id=organization.pk,
            )
            if url_path and apps.is_installed("baseapp_pages"):
                # Profile.save() already derived a handle from the name; replace it.
                profile.url_paths.all().delete()
                profile.create_url_path(profile_name=url_path)
            organization.profile = profile
            organization.save(update_fields=["profile"])
        return profile


def ensure_profiles_for_organizations(
    queryset: models.QuerySet | None = None, *, owner: AbstractBaseUser | None = None
) -> int:
    """
    Give every organization without a profile one (owned by `owner`, ownerless by
    default); returns how many were created.

    Meant for the data migration of a project adopting organizations, or a one-off
    command. It uses the current models, not migration state, so run it from a migration
    that comes after the profile and organization tables reach their current shape.
    """
    if queryset is None:
        Organization = swapper.load_model("baseapp_organizations", "Organization")
        queryset = Organization.objects.all()

    created = 0
    for organization in queryset.filter(profile__isnull=True).iterator():
        OrganizationService.ensure_profile(organization, owner=owner)
        created += 1
    return created


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

    def user_is_last_admin_of_ownerless_organization(self, user) -> bool:
        """
        Return `True` if `user` is the only active ADMIN of an organization whose profile
        has no owner — deleting the account would leave nobody able to manage it.
        """
        Organization = swapper.load_model("baseapp_organizations", "Organization")
        ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        admins = ProfileUserRole.objects.filter(
            role=ProfileUserRole.ProfileRoles.ADMIN,
            status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
        )
        profile_ids = set(
            admins.filter(
                user_id=user.id,
                profile__owner__isnull=True,
                profile_id__in=Organization.objects.values("profile_id"),
            ).values_list("profile_id", flat=True)
        )
        if not profile_ids:
            return False
        covered = set(
            admins.filter(profile_id__in=profile_ids)
            .exclude(user_id=user.id)
            .values_list("profile_id", flat=True)
        )
        return bool(profile_ids - covered)

    def get_account_deletion_block_reason(self, user) -> str | None:
        """
        Return why user's account cannot be deleted, or `None` if it can.

        An organization owner must transfer ownership or delete the organization
        before their account can be removed, and the only admin of an ownerless
        organization must first make another member an admin.
        """
        if self.user_owns_organization(user):
            return _(
                "Account cannot be deleted because you're the owner of an organization. Transfer ownership or delete the organization first."
            )
        if self.user_is_last_admin_of_ownerless_organization(user):
            return _(
                "Account cannot be deleted because you're the only admin of an organization. Make another member an admin first."
            )
        return None
