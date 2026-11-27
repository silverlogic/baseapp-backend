"""
Membership management: adding members, role changes, deactivation and removal, with a
last-admin guard.

These functions check business rules, not permissions: the caller (a mutation, a view, an
admin action) decides who may act and passes that user as `by` for the audit trail. The
caller also decides whether `by` may override the last-admin guard (`allow_last_admin`);
the GraphQL mutations allow it for holders of `<profile app>.override_last_admin`.
"""

import logging
from collections.abc import Iterable, Mapping

import swapper
from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from baseapp_profiles import signals
from baseapp_profiles.conf import protect_last_admin
from baseapp_profiles.exceptions import ProfileMembershipError

from ._utils import send_on_commit

logger = logging.getLogger(__name__)

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Status = ProfileUserRole.ProfileRoleStatus


# What the services decide; never set through `extra_fields`.
LIFECYCLE_FIELDS = frozenset(
    {
        "id",
        "pk",
        "role",
        "status",
        "user",
        "user_id",
        "profile",
        "profile_id",
        "invited_email",
        "invitation_token",
        "invitation_expires_at",
        "invited_at",
        "responded_at",
        "sent_count",
        "last_sent_at",
        "deactivated_at",
        "deactivated_by",
        "deactivated_by_id",
    }
)


def validate_role(role: int) -> None:
    """Refuse a role the model will not accept (see `assignable_roles()`)."""
    if role not in ProfileUserRole.assignable_roles():
        raise ProfileMembershipError(_("Invalid role type"), "invalid_input")


def set_extra_fields(membership: "ProfileUserRole", extra_fields: Mapping | None) -> list[str]:
    """
    Set the project's own columns on `membership` (field name -> value); returns the names.

    Raises `FieldDoesNotExist` for a name the concrete model does not have, so a typo in a
    project's mutation fails loudly rather than being dropped, and `ValueError` for a field
    BaseApp owns (`role`, `status`, `user`, ...): those only change through the services
    that check them, the last-admin guard included.
    """
    names = []
    for name, value in (extra_fields or {}).items():
        if name in LIFECYCLE_FIELDS:
            raise ValueError(f"extra_fields cannot set {name!r}; use the membership services")
        field = ProfileUserRole._meta.get_field(name)
        setattr(membership, field.attname if field.is_relation else name, value)
        names.append(field.attname if field.is_relation else name)
    return names


def is_last_admin_protected(profile: "Profile") -> bool:
    """
    Whether `profile` must always keep an active ADMIN.

    An ownerless profile is always protected: without an admin nobody could manage it. A
    profile with an owner is protected only when `BASEAPP_PROFILES_PROTECT_LAST_ADMIN` is on.
    """
    return profile.owner_id is None or protect_last_admin()


def ensure_not_last_admin(membership: "ProfileUserRole", *, allow_last_admin: bool = False) -> None:
    """
    Raise when taking `membership` out of service would leave its profile with no active
    ADMIN. Must run inside a transaction: it locks the profile's active admin rows, so two
    admins demoting each other at the same time cannot both succeed.

    `allow_last_admin` skips the guard, for someone the project trusts to leave a profile
    without an admin (say, support staff tidying up).
    """
    if allow_last_admin:
        return
    admin = ProfileUserRole.ProfileRoles.ADMIN
    if membership.role != admin or membership.status != ProfileUserRole.ProfileRoleStatus.ACTIVE:
        return
    if not is_last_admin_protected(membership.profile):
        return

    admins = ProfileUserRole.objects.filter(
        profile_id=membership.profile_id,
        role=admin,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    list(admins.select_for_update().order_by("pk").values_list("pk", flat=True))
    # An admin whose account is deactivated (say, being deleted) cannot manage the profile,
    # so does not count. Asked separately so the lock above stays on the admin rows.
    if not admins.filter(user__is_active=True).exclude(pk=membership.pk).exists():
        raise ProfileMembershipError(
            _("A profile must keep at least one active admin"), "last_admin"
        )


def lock_profile_memberships(profile_ids: Iterable[int]) -> None:
    """
    Serialize membership changes on these profiles until the transaction ends.

    Taken before any membership row is locked, so two requests that each hold one admin's
    row never wait on each other's (a deadlock): the second waits here and then sees what
    the first did. `no_key` keeps rows that reference the profile insertable meanwhile.
    """
    list(
        Profile.objects.select_for_update(no_key=True)
        .filter(pk__in=list(profile_ids))
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _lock(membership: "ProfileUserRole") -> None:
    """Lock the row and reload it, so the checks below see the committed state."""
    lock_profile_memberships([membership.profile_id])
    locked = list(
        ProfileUserRole.objects.select_for_update().filter(pk=membership.pk).values_list("pk")
    )
    if not locked:
        # Removed by another request since the caller loaded it.
        raise ProfileMembershipError(_("Role not found"), "not_found")
    membership.refresh_from_db()


def add_members(
    profile: "Profile",
    users: Iterable[AbstractBaseUser],
    *,
    role: int | None = None,
    by: AbstractBaseUser | None = None,
    extra_fields: Mapping | None = None,
) -> list["ProfileUserRole"]:
    """
    Add `users` to `profile` as ACTIVE members with `role` (MANAGER by default), skipping
    the invitation step. `extra_fields` is set on every new row. Sends `member_added` for
    each.

    All-or-nothing: the owner (`cannot_add_owner`) or anyone who already holds an open row
    (`already_member`) refuses the whole batch. With invitation history on, a declined,
    expired or cancelled invitation is only a record and does not stop the person.
    """
    from baseapp_profiles.conf import keep_invitation_history

    if role is None:
        role = ProfileUserRole.ProfileRoles.MANAGER
    validate_role(role)

    # De-duplicated, keeping the order the caller gave.
    users = list({user.pk: user for user in users}.values())
    if any(profile.is_owned_by(user) for user in users):
        raise ProfileMembershipError(
            _("The profile owner cannot be added as a member"), "cannot_add_owner"
        )

    with transaction.atomic():
        lock_profile_memberships([profile.pk])
        existing = ProfileUserRole.objects.filter(
            profile=profile, user_id__in=[user.pk for user in users]
        )
        if keep_invitation_history():
            existing = existing.open()
        if existing.exists():
            raise ProfileMembershipError(
                _("One or more of the selected users are already members of this profile"),
                "already_member",
            )
        memberships = []
        try:
            with transaction.atomic():
                # Saved one at a time rather than with bulk_create: bulk_create issues no
                # post_save, and projects hang membership bookkeeping off that signal.
                for user in users:
                    membership = ProfileUserRole(
                        user=user, profile=profile, role=role, status=Status.ACTIVE
                    )
                    set_extra_fields(membership, extra_fields)
                    membership.save()
                    memberships.append(membership)
        except IntegrityError as error:
            logger.exception("Failed to add members to profile %s", profile.pk)
            # A concurrent add got there first; anything else is reported generically.
            # The same question as above: with history on, a closed row is not a conflict.
            if existing.exists():
                raise ProfileMembershipError(
                    _("One or more of the selected users are already members of this profile"),
                    "already_member",
                ) from error
            raise ProfileMembershipError(
                _("Unable to add the selected members"), "add_member_failed"
            ) from error
        for membership in memberships:
            send_on_commit(signals.member_added, membership, by=by)
    return memberships


def update_member(
    membership: "ProfileUserRole",
    *,
    role: int | None = None,
    by: AbstractBaseUser | None = None,
    extra_fields: Mapping | None = None,
    allow_last_admin: bool = False,
) -> "ProfileUserRole":
    """
    Change `membership`'s role and/or the project's own columns (`extra_fields`).

    Demoting the last active admin is refused unless `allow_last_admin`. Sends
    `member_role_changed` when the role changes.
    """
    if role is not None:
        validate_role(role)
    with transaction.atomic():
        _lock(membership)
        update_fields = set_extra_fields(membership, extra_fields)
        old_role = membership.role
        role_changed = role is not None and role != old_role
        if role_changed:
            if role != ProfileUserRole.ProfileRoles.ADMIN:
                ensure_not_last_admin(membership, allow_last_admin=allow_last_admin)
            membership.role = role
            update_fields.append("role")
        if update_fields:
            membership.save(update_fields=update_fields)
        if role_changed:
            send_on_commit(
                signals.member_role_changed, membership, old_role=old_role, new_role=role, by=by
            )
    return membership


def change_member_role(
    membership: "ProfileUserRole",
    role: int,
    *,
    by: AbstractBaseUser | None = None,
    allow_last_admin: bool = False,
) -> "ProfileUserRole":
    """Give `membership` a new role, refusing to demote the last active admin."""
    return update_member(membership, role=role, by=by, allow_last_admin=allow_last_admin)


def deactivate_member(
    membership: "ProfileUserRole",
    *,
    by: AbstractBaseUser | None = None,
    reason: str = "",
    extra_fields: Mapping | None = None,
    allow_last_admin: bool = False,
) -> "ProfileUserRole":
    """
    Mark an ACTIVE member INACTIVE: they keep their row but stop reaching the profile.

    `reason` is not stored; it is passed to `member_deactivated` for the project to record
    or include in a notification. `extra_fields` is saved with the status change.
    """
    with transaction.atomic():
        _lock(membership)
        if membership.status != ProfileUserRole.ProfileRoleStatus.ACTIVE:
            raise ProfileMembershipError(
                _("Only active members can be deactivated"), "invalid_status"
            )
        ensure_not_last_admin(membership, allow_last_admin=allow_last_admin)
        update_fields = set_extra_fields(membership, extra_fields)
        membership.status = ProfileUserRole.ProfileRoleStatus.INACTIVE
        membership.deactivated_at = timezone.now()
        membership.deactivated_by = by
        membership.save(
            update_fields=[*update_fields, "status", "deactivated_at", "deactivated_by"]
        )
        send_on_commit(signals.member_deactivated, membership, by=by, reason=reason or "")
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


def remove_member(
    membership: "ProfileUserRole",
    *,
    by: AbstractBaseUser | None = None,
    allow_last_admin: bool = False,
) -> None:
    """
    Delete a membership, refusing to remove the last active admin (unless
    `allow_last_admin`).

    `member_removed` is sent with the deleted instance (its `pk` is then `None`) and the
    former primary key as `pk`.
    """
    with transaction.atomic():
        _lock(membership)
        ensure_not_last_admin(membership, allow_last_admin=allow_last_admin)
        pk = membership.pk
        membership.delete()
        send_on_commit(signals.member_removed, membership, pk=pk, by=by)
