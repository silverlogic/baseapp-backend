import logging
from datetime import timedelta

import graphene
import swapper
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_object_type_for_model,
    get_pk_from_relay_id,
    login_required,
)
from baseapp_profiles.constants import INVITATION_EXPIRATION_DAYS

from ..object_types import ProfileRoleTypesEnum

logger = logging.getLogger(__name__)

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_user_role_app_label = ProfileUserRole._meta.app_label


def _get_invitation_by_token(token: str):
    try:
        return ProfileUserRole.objects.get(invitation_token=token)
    except ProfileUserRole.DoesNotExist:
        raise GraphQLError(
            str(_("Invalid invitation token")),
            extensions={"code": "invalid_token"},
        )


def _get_invitation_by_id(invitation_id: str):
    invitation_pk = get_pk_from_relay_id(invitation_id)
    try:
        return ProfileUserRole.objects.get(pk=invitation_pk)
    except ProfileUserRole.DoesNotExist:
        raise GraphQLError(
            str(_("Invitation not found")),
            extensions={"code": "not_found"},
        )


def _validate_invitation_for_response(invitation, user) -> None:
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


def _reset_invitation_for_send(invitation, role=None, user=None) -> None:
    invitation.status = ProfileUserRole.ProfileRoleStatus.PENDING
    invitation.invited_at = timezone.now()
    invitation.invitation_expires_at = timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS)
    invitation.responded_at = None
    invitation.generate_invitation_token()
    if role is not None:
        invitation.role = role
    if user is not None:
        invitation.user = user


def _create_or_reset_invitation(profile, normalized_email: str, role, invited_user):
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
            _reset_invitation_for_send(existing_role, role=role, user=invited_user)
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


class ProfileSendInvitation(RelayMutation):
    profile_user_roles = graphene.List(get_object_type_for_model(ProfileUserRole))
    emails_sent = graphene.Int()

    class Input:
        profile_id = graphene.ID(required=True)
        emails = graphene.List(graphene.NonNull(graphene.String), required=True)
        role = graphene.Field(ProfileRoleTypesEnum, required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        from django.contrib.auth import get_user_model

        from baseapp_profiles.emails import send_invitation_email

        profile_id = input.get("profile_id")
        emails = input.get("emails") or []
        role = input.get("role")

        profile_pk = get_pk_from_relay_id(profile_id)
        try:
            profile = Profile.objects.get(pk=profile_pk)
        except Profile.DoesNotExist:
            raise GraphQLError(
                str(_("Profile not found")),
                extensions={"code": "not_found"},
            )

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        # Normalize + de-duplicate the emails, preserving order.
        normalized_emails = []
        seen = set()
        for email in emails:
            normalized = (email or "").strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_emails.append(normalized)

        if not normalized_emails:
            raise GraphQLError(
                str(_("At least one email is required")),
                extensions={"code": "invalid_input"},
            )

        User = get_user_model()

        # Create/revive every invitation in one transaction — a hard conflict on any
        # email rolls back the whole batch so the caller can fix it and retry.
        invitations = []
        with transaction.atomic():
            for normalized_email in normalized_emails:
                try:
                    invited_user = User.objects.get(email__iexact=normalized_email)
                except User.DoesNotExist:
                    invited_user = None
                invitations.append(
                    _create_or_reset_invitation(profile, normalized_email, role, invited_user)
                )

        emails_sent = 0
        for invitation in invitations:
            try:
                send_invitation_email(invitation, info.context.user)
                emails_sent += 1
            except Exception:
                logger.exception("Failed to send invitation email to %s", invitation.invited_email)

        return cls(profile_user_roles=invitations, emails_sent=emails_sent)


class ProfileAcceptInvitation(RelayMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))
    profile = graphene.Field(get_object_type_for_model(Profile))

    class Input:
        token = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        token = input.get("token")

        invitation = _get_invitation_by_token(token)
        _validate_invitation_for_response(invitation, info.context.user)

        invitation.status = ProfileUserRole.ProfileRoleStatus.ACTIVE
        invitation.responded_at = timezone.now()
        invitation.save()

        return ProfileAcceptInvitation(profile_user_role=invitation, profile=invitation.profile)


class ProfileDeclineInvitation(RelayMutation):
    success = graphene.Boolean()

    class Input:
        token = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        token = input.get("token")

        invitation = _get_invitation_by_token(token)
        _validate_invitation_for_response(invitation, info.context.user)

        invitation.status = ProfileUserRole.ProfileRoleStatus.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()

        return ProfileDeclineInvitation(success=True)


class ProfileCancelInvitation(RelayMutation):
    success = graphene.Boolean()

    class Input:
        invitation_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        invitation_id = input.get("invitation_id")

        invitation = _get_invitation_by_id(invitation_id)

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.delete_profileuserrole", invitation.profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if invitation.status != ProfileUserRole.ProfileRoleStatus.PENDING:
            raise GraphQLError(
                str(_("Can only cancel pending invitations")),
                extensions={"code": "invalid_status"},
            )

        invitation.delete()

        return ProfileCancelInvitation(success=True)


class ProfileResendInvitation(RelayMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))
    email_sent = graphene.Boolean()

    class Input:
        invitation_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        from baseapp_profiles.emails import send_invitation_email

        invitation_id = input.get("invitation_id")

        invitation = _get_invitation_by_id(invitation_id)

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", invitation.profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if invitation.status not in [
            ProfileUserRole.ProfileRoleStatus.EXPIRED,
            ProfileUserRole.ProfileRoleStatus.PENDING,
        ]:
            raise GraphQLError(
                str(_("Can only resend expired or pending invitations")),
                extensions={"code": "invalid_status"},
            )

        _reset_invitation_for_send(invitation)
        invitation.save()

        email_sent = True
        try:
            send_invitation_email(invitation, info.context.user)
        except Exception:
            logger.exception("Failed to resend invitation email to %s", invitation.invited_email)
            email_sent = False

        return ProfileResendInvitation(profile_user_role=invitation, email_sent=email_sent)
