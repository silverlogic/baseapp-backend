"""
Membership management: role changes, deactivation and removal, with a last-admin guard.

These functions check business rules, not permissions: the caller (a mutation, a view, an
admin action) decides who may act and passes that user as `by` for the audit trail.
"""

import swapper
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from baseapp_profiles import signals
from baseapp_profiles.conf import protect_last_admin
from baseapp_profiles.exceptions import ProfileMembershipError

from ._utils import send_on_commit

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


def validate_role(role: int) -> None:
    """Refuse a role the model will not accept (see `assignable_roles()`)."""
    if role not in ProfileUserRole.assignable_roles():
        raise ProfileMembershipError(_("Invalid role type"), "invalid_input")


def is_last_admin_protected(profile: "Profile") -> bool:
    """
    Whether `profile` must always keep an active ADMIN.

    An ownerless profile is always protected: without an admin nobody could manage it. A
    profile with an owner is protected only when `BASEAPP_PROFILES_PROTECT_LAST_ADMIN` is on.
    """
    return profile.owner_id is None or protect_last_admin()


def ensure_not_last_admin(membership: "ProfileUserRole") -> None:
    """
    Raise when taking `membership` out of service would leave its profile with no active
    ADMIN. Must run inside a transaction: it locks the profile's active admin rows, so two
    admins demoting each other at the same time cannot both succeed.
    """
    admin = ProfileUserRole.ProfileRoles.ADMIN
    if membership.role != admin or membership.status != ProfileUserRole.ProfileRoleStatus.ACTIVE:
        return
    if not is_last_admin_protected(membership.profile):
        return

    admin_pks = list(
        ProfileUserRole.objects.select_for_update()
        .filter(
            profile_id=membership.profile_id,
            role=admin,
            status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
        )
        .values_list("pk", flat=True)
    )
    if not [pk for pk in admin_pks if pk != membership.pk]:
        raise ProfileMembershipError(
            _("A profile must keep at least one active admin"), "last_admin"
        )


def _lock(membership: "ProfileUserRole") -> None:
    """Lock the row and reload it, so the checks below see the committed state."""
    list(ProfileUserRole.objects.select_for_update().filter(pk=membership.pk).values_list("pk"))
    membership.refresh_from_db()


def change_member_role(
    membership: "ProfileUserRole", role: int, *, by: AbstractBaseUser | None = None
) -> "ProfileUserRole":
    """Give `membership` a new role, refusing to demote the last active admin."""
    validate_role(role)
    with transaction.atomic():
        _lock(membership)
        old_role = membership.role
        if old_role == role:
            return membership
        if role != ProfileUserRole.ProfileRoles.ADMIN:
            ensure_not_last_admin(membership)
        membership.role = role
        membership.save(update_fields=["role"])
        send_on_commit(
            signals.member_role_changed, membership, old_role=old_role, new_role=role, by=by
        )
    return membership


def deactivate_member(
    membership: "ProfileUserRole", *, by: AbstractBaseUser | None = None
) -> "ProfileUserRole":
    """Mark an ACTIVE member INACTIVE: they keep their row but stop reaching the profile."""
    with transaction.atomic():
        _lock(membership)
        if membership.status != ProfileUserRole.ProfileRoleStatus.ACTIVE:
            raise ProfileMembershipError(
                _("Only active members can be deactivated"), "invalid_status"
            )
        ensure_not_last_admin(membership)
        membership.status = ProfileUserRole.ProfileRoleStatus.INACTIVE
        membership.deactivated_at = timezone.now()
        membership.deactivated_by = by
        membership.save(update_fields=["status", "deactivated_at", "deactivated_by"])
        send_on_commit(signals.member_deactivated, membership, by=by)
    return membership


def reactivate_member(
    membership: "ProfileUserRole", *, by: AbstractBaseUser | None = None
) -> "ProfileUserRole":
    """Restore an INACTIVE member to ACTIVE."""
    with transaction.atomic():
        _lock(membership)
        if (
            membership.status != ProfileUserRole.ProfileRoleStatus.INACTIVE
            or membership.user_id is None
        ):
            raise ProfileMembershipError(
                _("Only deactivated members can be reactivated"), "invalid_status"
            )
        membership.status = ProfileUserRole.ProfileRoleStatus.ACTIVE
        membership.deactivated_at = None
        membership.deactivated_by = None
        membership.save(update_fields=["status", "deactivated_at", "deactivated_by"])
        send_on_commit(signals.member_reactivated, membership, by=by)
    return membership


def remove_member(membership: "ProfileUserRole", *, by: AbstractBaseUser | None = None) -> None:
    """
    Delete a membership, refusing to remove the last active admin.

    `member_removed` is sent with the deleted instance (its `pk` is then `None`) and the
    former primary key as `pk`.
    """
    with transaction.atomic():
        _lock(membership)
        ensure_not_last_admin(membership)
        pk = membership.pk
        membership.delete()
        send_on_commit(signals.member_removed, membership, pk=pk, by=by)
