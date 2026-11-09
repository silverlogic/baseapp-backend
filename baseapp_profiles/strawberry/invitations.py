from datetime import timedelta

import swapper
from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_profiles.constants import INVITATION_EXPIRATION_DAYS

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


def validate_assignable_role(role: int) -> None:
    """
    Refuse a role the model will not accept.

    Every value a project declares reaches the API through the `ProfileRoles` enum,
    including any it reserves for a later phase. Without this the write goes through to
    whatever constraint guards the column, and the caller gets an unhandled database
    error instead of being told the role is invalid.
    """
    if role not in ProfileUserRole.assignable_roles():
        raise GraphQLError(
            str(_("Invalid role type")),
            extensions={"code": "invalid_input"},
        )


def get_invitation_by_token(token: str) -> "ProfileUserRole":
    try:
        return ProfileUserRole.objects.get(invitation_token=token)
    except ProfileUserRole.DoesNotExist:
        raise GraphQLError(
            str(_("Invalid invitation token")),
            extensions={"code": "invalid_token"},
        )


def get_invitation_by_id(invitation_id: str) -> "ProfileUserRole":
    invitation_pk = get_pk_from_relay_id(invitation_id)
    try:
        return ProfileUserRole.objects.get(pk=invitation_pk)
    except ProfileUserRole.DoesNotExist:
        raise GraphQLError(
            str(_("Invitation not found")),
            extensions={"code": "not_found"},
        )


def validate_invitation_for_response(invitation, user) -> None:
    if invitation.is_invitation_expired():
        invitation.status = ProfileUserRole.ProfileRoleStatus.EXPIRED
        invitation.save()
        raise GraphQLError(
            str(_("This invitation has expired")),
            extensions={"code": "expired_invitation"},
        )

    if invitation.status != ProfileUserRole.ProfileRoleStatus.PENDING:
        raise GraphQLError(
            str(_("This invitation has already been responded to")),
            extensions={"code": "already_responded"},
        )

    if not invitation.user:
        user_email = (user.email or "").casefold()
        invited_email = (invitation.invited_email or "").casefold()
        if user_email != invited_email:
            raise GraphQLError(
                str(_("This invitation was sent to a different user")),
                extensions={"code": "wrong_user"},
            )
        invitation.user = user
    elif invitation.user.id != user.id:
        raise GraphQLError(
            str(_("This invitation was sent to a different user")),
            extensions={"code": "wrong_user"},
        )


def reset_invitation_for_send(invitation, role=None, user=None) -> None:
    invitation.status = ProfileUserRole.ProfileRoleStatus.PENDING
    invitation.invited_at = timezone.now()
    invitation.invitation_expires_at = timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS)
    invitation.responded_at = None
    invitation.generate_invitation_token()
    if role is not None:
        invitation.role = role
    if user is not None:
        invitation.user = user


def create_or_reset_invitation(
    profile, normalized_email: str, role, invited_user
) -> "ProfileUserRole":
    """Create a fresh invitation for ``normalized_email`` on ``profile`` (or revive an
    existing declined/inactive/expired one). Must run inside a transaction — it takes a
    ``select_for_update`` lock. Raises ``GraphQLError`` on a hard conflict (the email is
    already an active member, or has a still-valid pending invitation)."""
    existing_role = (
        ProfileUserRole.objects.select_for_update()
        .filter(profile=profile, invited_email__iexact=normalized_email)
        .first()
    )

    if existing_role:
        if existing_role.status == ProfileUserRole.ProfileRoleStatus.ACTIVE:
            raise GraphQLError(
                str(
                    _("%(email)s is already a member of this profile") % {"email": normalized_email}
                ),
                extensions={"code": "already_member"},
            )

        if existing_role.status == ProfileUserRole.ProfileRoleStatus.PENDING:
            if not existing_role.is_invitation_expired():
                raise GraphQLError(
                    str(
                        _("An invitation has already been sent to %(email)s")
                        % {"email": normalized_email}
                    ),
                    extensions={"code": "duplicate_invitation"},
                )
            existing_role.status = ProfileUserRole.ProfileRoleStatus.EXPIRED

        if existing_role.status in [
            ProfileUserRole.ProfileRoleStatus.DECLINED,
            ProfileUserRole.ProfileRoleStatus.INACTIVE,
            ProfileUserRole.ProfileRoleStatus.EXPIRED,
        ]:
            reset_invitation_for_send(existing_role, role=role, user=invited_user)
            existing_role.save()
            return existing_role

        raise GraphQLError(
            str(_("Cannot send invitation in current state")),
            extensions={"code": "invalid_status"},
        )

    try:
        invitation = ProfileUserRole.objects.create(
            profile=profile,
            user=invited_user,
            invited_email=normalized_email,
            role=role,
            status=ProfileUserRole.ProfileRoleStatus.PENDING,
            invited_at=timezone.now(),
            invitation_expires_at=(timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS)),
        )
        invitation.generate_invitation_token()
        invitation.save()
        return invitation
    except IntegrityError:
        raise GraphQLError(
            str(
                _("An invitation has already been sent to %(email)s") % {"email": normalized_email}
            ),
            extensions={"code": "duplicate_invitation"},
        )
