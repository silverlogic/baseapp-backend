import logging

import strawberry
import swapper
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import (
    add_request_files,
    input_data,
    serializer_errors,
)

from .invitations import (
    create_or_reset_invitation,
    get_invitation_by_id,
    get_invitation_by_token,
    reset_invitation_for_send,
    validate_assignable_role,
    validate_invitation_for_response,
)
from .serializers import ProfileCreateSerializer, ProfileUpdateSerializer
from .types import ProfileLazyType, ProfileRolesEnum, ProfileUserRoleLazyType

logger = logging.getLogger(__name__)

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_app_label = Profile._meta.app_label
profile_user_role_app_label = ProfileUserRole._meta.app_label


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


@strawberry.input(name="ProfileCreateInput")
class ProfileCreateInput(RelayMutationInput):
    name: str
    owner: str | None = UNSET
    image: str | None = UNSET
    banner_image: str | None = UNSET
    biography: str | None = UNSET
    url_path: str | None = UNSET
    target: str | None = UNSET
    target_content_type: str | None = UNSET
    target_object_id: int | None = UNSET


@strawberry.type(name="ProfileCreatePayload")
class ProfileCreatePayload(RelayMutationPayload):
    profile: Edge[ProfileLazyType] | None = None


@strawberry.input(name="ProfileUpdateInput")
class ProfileUpdateInput(RelayMutationInput):
    id: strawberry.ID
    owner: str | None = UNSET
    name: str | None = UNSET
    image: str | None = UNSET
    banner_image: str | None = UNSET
    biography: str | None = UNSET
    url_path: str | None = UNSET
    phone_number: str | None = UNSET


@strawberry.type(name="ProfileUpdatePayload")
class ProfileUpdatePayload(RelayMutationPayload):
    profile: ProfileLazyType | None = None


@strawberry.input(name="ProfileDeleteInput")
class ProfileDeleteInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="ProfileDeletePayload")
class ProfileDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None


@strawberry.input(name="ProfileUserRoleCreateInput")
class ProfileUserRoleCreateInput(RelayMutationInput):
    profile_id: strawberry.ID
    users_ids: list[strawberry.ID | None] | None = UNSET
    emails_to_invite: list[str | None] | None = UNSET
    role_type: ProfileRolesEnum | None = None


@strawberry.type(name="ProfileUserRoleCreatePayload")
class ProfileUserRoleCreatePayload(RelayMutationPayload):
    profile_user_roles: list[ProfileUserRoleLazyType | None] | None = None


@strawberry.input(name="ProfileUserRoleUpdateInput")
class ProfileUserRoleUpdateInput(RelayMutationInput):
    profile_id: strawberry.ID
    user_id: strawberry.ID
    role_type: ProfileRolesEnum


@strawberry.type(name="ProfileUserRoleUpdatePayload")
class ProfileUserRoleUpdatePayload(RelayMutationPayload):
    profile_user_role: ProfileUserRoleLazyType | None = None


@strawberry.input(name="ProfileUserRoleDeleteInput")
class ProfileUserRoleDeleteInput(RelayMutationInput):
    profile_id: strawberry.ID
    user_id: strawberry.ID


@strawberry.type(name="ProfileUserRoleDeletePayload")
class ProfileUserRoleDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None


@strawberry.input(name="ProfileSendInvitationInput")
class ProfileSendInvitationInput(RelayMutationInput):
    profile_id: strawberry.ID
    emails: list[str]
    role: ProfileRolesEnum


@strawberry.type(name="ProfileSendInvitationPayload")
class ProfileSendInvitationPayload(RelayMutationPayload):
    profile_user_roles: list[ProfileUserRoleLazyType | None] | None = None
    emails_sent: int | None = None


@strawberry.input(name="ProfileAcceptInvitationInput")
class ProfileAcceptInvitationInput(RelayMutationInput):
    token: str


@strawberry.type(name="ProfileAcceptInvitationPayload")
class ProfileAcceptInvitationPayload(RelayMutationPayload):
    profile_user_role: ProfileUserRoleLazyType | None = None
    profile: ProfileLazyType | None = None


@strawberry.input(name="ProfileDeclineInvitationInput")
class ProfileDeclineInvitationInput(RelayMutationInput):
    token: str


@strawberry.type(name="ProfileDeclineInvitationPayload")
class ProfileDeclineInvitationPayload(RelayMutationPayload):
    success: bool | None = None


@strawberry.input(name="ProfileCancelInvitationInput")
class ProfileCancelInvitationInput(RelayMutationInput):
    invitation_id: strawberry.ID


@strawberry.type(name="ProfileCancelInvitationPayload")
class ProfileCancelInvitationPayload(RelayMutationPayload):
    success: bool | None = None


@strawberry.input(name="ProfileResendInvitationInput")
class ProfileResendInvitationInput(RelayMutationInput):
    invitation_id: strawberry.ID


@strawberry.type(name="ProfileResendInvitationPayload")
class ProfileResendInvitationPayload(RelayMutationPayload):
    profile_user_role: ProfileUserRoleLazyType | None = None
    email_sent: bool | None = None


@strawberry.type
class ProfilesMutations:
    @relay_mutation(login_required=True)
    def profile_create(self, info: Info, input: ProfileCreateInput) -> ProfileCreatePayload | None:
        if not info.context.user.has_perm(f"{profile_app_label}.add_profile"):
            raise _permission_error()

        serializer = ProfileCreateSerializer(
            data=add_request_files(info, input_data(input)), context={"request": info.context}
        )
        if not serializer.is_valid():
            return ProfileCreatePayload(errors=serializer_errors(serializer))
        # TODO: get target using get_obj_from_relay_id and inject into the serializer to be used
        # by validate and create methods
        obj = serializer.save()
        return ProfileCreatePayload(profile=Edge(node=obj, cursor=None))

    @relay_mutation(login_required=True)
    def profile_update(self, info: Info, input: ProfileUpdateInput) -> ProfileUpdatePayload | None:
        if service := shared_services.get("activity_log"):
            service.set_public_activity(verb="baseapp_profiles.update_profile")

        data = add_request_files(info, input_data(input, exclude=("id",)))
        try:
            instance = Profile.objects.get(pk=get_pk_from_relay_id(input.id))
        except Profile.DoesNotExist:
            raise ValueError(str(_("Profile not found")))

        if not info.context.user.has_perm(f"{profile_app_label}.change_profile", instance):
            raise _permission_error()

        serializer = ProfileUpdateSerializer(
            instance=instance, data=data, partial=True, context={"request": info.context}
        )
        if not serializer.is_valid():
            return ProfileUpdatePayload(errors=serializer_errors(serializer))
        return ProfileUpdatePayload(profile=serializer.save())

    @relay_mutation(login_required=True)
    def profile_delete(self, info: Info, input: ProfileDeleteInput) -> ProfileDeletePayload | None:
        obj = Profile.objects.filter(pk=get_pk_from_relay_id(input.id)).first()
        if not obj or not info.context.user.has_perm(f"{profile_app_label}.delete_profile", obj):
            raise _permission_error()
        obj.delete()
        return ProfileDeletePayload(deleted_id=input.id)

    @relay_mutation(login_required=True)
    @transaction.atomic
    def profile_user_role_create(
        self, info: Info, input: ProfileUserRoleCreateInput
    ) -> ProfileUserRoleCreatePayload | None:
        profile_pk = get_pk_from_relay_id(input.profile_id)
        role_type = input.role_type
        try:
            profile = Profile.objects.get(pk=profile_pk)
        except Profile.DoesNotExist:
            raise GraphQLError(str(_("Profile not found")))

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", profile
        ):
            raise _permission_error()
        if not role_type:
            role_type = ProfileUserRole.ProfileRoles.MANAGER
        else:
            validate_assignable_role(role_type)

        # TODO on BA-2426: send invitation to new users emails (input.emails_to_invite)

        # De-duplicate the requested users, then reject any that are already members so the
        # client gets a clear message instead of a raw unique-constraint (IntegrityError).
        requested_user_pks = list(
            dict.fromkeys(get_pk_from_relay_id(user_id) for user_id in (input.users_ids or []))
        )
        if str(profile.owner_id) in {str(pk) for pk in requested_user_pks}:
            raise GraphQLError(
                str(_("The profile owner cannot be added as a member")),
                extensions={"code": "cannot_add_owner"},
            )
        if ProfileUserRole.objects.filter(
            profile_id=profile_pk, user_id__in=requested_user_pks
        ).exists():
            raise GraphQLError(
                str(_("One or more of the selected users are already members of this profile")),
                extensions={"code": "already_member"},
            )

        try:
            with transaction.atomic():
                # Members added directly (rather than invited) are active immediately: there is
                # no acceptance step, and an INACTIVE membership grants no access.
                # Saved one at a time (not bulk_create) so post_save fires for projects that
                # hang membership bookkeeping off it.
                profile_user_roles = [
                    ProfileUserRole.objects.create(
                        user_id=user_pk,
                        profile_id=profile_pk,
                        role=role_type,
                        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
                    )
                    for user_pk in requested_user_pks
                ]
        except IntegrityError as error:
            logger.exception("Failed to add members to profile %s", profile_pk)
            # Only report "already_member" if a membership actually exists now (race with the
            # pre-check); any other integrity failure returns a generic error.
            if ProfileUserRole.objects.filter(
                profile_id=profile_pk, user_id__in=requested_user_pks
            ).exists():
                raise GraphQLError(
                    str(_("One or more of the selected users are already members of this profile")),
                    extensions={"code": "already_member"},
                ) from error
            raise GraphQLError(
                str(_("Unable to add the selected members")),
                extensions={"code": "add_member_failed"},
            ) from error

        return ProfileUserRoleCreatePayload(profile_user_roles=profile_user_roles)

    @relay_mutation(login_required=True)
    def profile_user_role_update(
        self, info: Info, input: ProfileUserRoleUpdateInput
    ) -> ProfileUserRoleUpdatePayload | None:
        role_type = input.role_type
        validate_assignable_role(role_type)
        user_pk = get_pk_from_relay_id(input.user_id)
        profile_pk = get_pk_from_relay_id(input.profile_id)

        try:
            obj = ProfileUserRole.objects.get(user_id=user_pk, profile_id=profile_pk)
        except ProfileUserRole.DoesNotExist:
            raise GraphQLError(str(_("Role not found")), extensions={"code": "not_found"})

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.change_profileuserrole", obj.profile
        ):
            raise _permission_error()

        obj.role = role_type
        obj.save()
        return ProfileUserRoleUpdatePayload(profile_user_role=obj)

    @relay_mutation(login_required=True)
    def profile_user_role_delete(
        self, info: Info, input: ProfileUserRoleDeleteInput
    ) -> ProfileUserRoleDeletePayload | None:
        profile_pk = get_pk_from_relay_id(input.profile_id)
        user_pk = get_pk_from_relay_id(input.user_id)
        try:
            obj = ProfileUserRole.objects.get(user_id=user_pk, profile_id=profile_pk)
        except ProfileUserRole.DoesNotExist:
            raise GraphQLError(str(_("User role not found")), extensions={"code": "not_found"})

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.delete_profileuserrole", obj.profile
        ):
            raise _permission_error()

        deleted_id = obj.relay_id
        obj.delete()
        return ProfileUserRoleDeletePayload(deleted_id=deleted_id)

    @relay_mutation(login_required=True)
    def profile_send_invitation(
        self, info: Info, input: ProfileSendInvitationInput
    ) -> ProfileSendInvitationPayload | None:
        from baseapp_profiles.emails import send_invitation_email

        role = input.role
        validate_assignable_role(role)

        try:
            profile = Profile.objects.get(pk=get_pk_from_relay_id(input.profile_id))
        except Profile.DoesNotExist:
            raise GraphQLError(str(_("Profile not found")), extensions={"code": "not_found"})

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", profile
        ):
            raise _permission_error()

        # Normalize + de-duplicate the emails, preserving order.
        normalized_emails = list(
            dict.fromkeys(
                normalized
                for email in input.emails
                if (normalized := (email or "").strip().lower())
            )
        )
        if not normalized_emails:
            raise GraphQLError(
                str(_("At least one email is required")), extensions={"code": "invalid_input"}
            )

        User = get_user_model()

        # One transaction: a hard conflict on any email rolls back the whole batch.
        invitations = []
        with transaction.atomic():
            for normalized_email in normalized_emails:
                try:
                    invited_user = User.objects.get(email__iexact=normalized_email)
                except User.DoesNotExist:
                    invited_user = None
                invitations.append(
                    create_or_reset_invitation(profile, normalized_email, role, invited_user)
                )

        emails_sent = 0
        for invitation in invitations:
            try:
                send_invitation_email(invitation, info.context.user)
                emails_sent += 1
            except Exception:
                logger.exception("Failed to send invitation email to %s", invitation.invited_email)

        return ProfileSendInvitationPayload(profile_user_roles=invitations, emails_sent=emails_sent)

    @relay_mutation(login_required=True)
    def profile_accept_invitation(
        self, info: Info, input: ProfileAcceptInvitationInput
    ) -> ProfileAcceptInvitationPayload | None:
        invitation = get_invitation_by_token(input.token)
        validate_invitation_for_response(invitation, info.context.user)

        if invitation.profile.owner_id == info.context.user.id:
            raise GraphQLError(
                str(_("The profile owner cannot accept an invitation to their own profile")),
                extensions={"code": "cannot_add_owner"},
            )

        invitation.status = ProfileUserRole.ProfileRoleStatus.ACTIVE
        invitation.responded_at = timezone.now()
        invitation.save()
        return ProfileAcceptInvitationPayload(
            profile_user_role=invitation, profile=invitation.profile
        )

    @relay_mutation(login_required=True)
    def profile_decline_invitation(
        self, info: Info, input: ProfileDeclineInvitationInput
    ) -> ProfileDeclineInvitationPayload | None:
        invitation = get_invitation_by_token(input.token)
        validate_invitation_for_response(invitation, info.context.user)

        invitation.status = ProfileUserRole.ProfileRoleStatus.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()
        return ProfileDeclineInvitationPayload(success=True)

    @relay_mutation(login_required=True)
    def profile_cancel_invitation(
        self, info: Info, input: ProfileCancelInvitationInput
    ) -> ProfileCancelInvitationPayload | None:
        invitation = get_invitation_by_id(input.invitation_id)

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.delete_profileuserrole", invitation.profile
        ):
            raise _permission_error()

        if invitation.status != ProfileUserRole.ProfileRoleStatus.PENDING:
            raise GraphQLError(
                str(_("Can only cancel pending invitations")),
                extensions={"code": "invalid_status"},
            )

        invitation.delete()
        return ProfileCancelInvitationPayload(success=True)

    @relay_mutation(login_required=True)
    def profile_resend_invitation(
        self, info: Info, input: ProfileResendInvitationInput
    ) -> ProfileResendInvitationPayload | None:
        from baseapp_profiles.emails import send_invitation_email

        invitation = get_invitation_by_id(input.invitation_id)

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", invitation.profile
        ):
            raise _permission_error()

        if invitation.status not in [
            ProfileUserRole.ProfileRoleStatus.EXPIRED,
            ProfileUserRole.ProfileRoleStatus.PENDING,
        ]:
            raise GraphQLError(
                str(_("Can only resend expired or pending invitations")),
                extensions={"code": "invalid_status"},
            )

        reset_invitation_for_send(invitation)
        invitation.save()

        email_sent = True
        try:
            send_invitation_email(invitation, info.context.user)
        except Exception:
            logger.exception("Failed to resend invitation email to %s", invitation.invited_email)
            email_sent = False

        return ProfileResendInvitationPayload(profile_user_role=invitation, email_sent=email_sent)
