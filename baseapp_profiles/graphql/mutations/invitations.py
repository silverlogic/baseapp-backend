import logging

import graphene
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_object_type_for_model,
    get_pk_from_relay_id,
    login_required,
)
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as invitation_service

from ..object_types import ProfileRoleTypesEnum
from .base import ExtensibleMutation
from .roles import validate_assignable_role

logger = logging.getLogger(__name__)

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_user_role_app_label = ProfileUserRole._meta.app_label


def as_graphql_error(error: ProfileMembershipError) -> GraphQLError:
    """Report a refused membership operation with its stable code in `extensions.code`."""
    return GraphQLError(error.message, extensions={"code": error.code})


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


def _get_invitation_by_id(invitation_id: str) -> "ProfileUserRole":
    invitation_pk = get_pk_from_relay_id(invitation_id)
    try:
        return ProfileUserRole.objects.select_related("profile").get(pk=invitation_pk)
    except ProfileUserRole.DoesNotExist:
        raise GraphQLError(
            str(_("Invitation not found")),
            extensions={"code": "not_found"},
        )


class ProfileInviteeInput(graphene.InputObjectType):
    email = graphene.String(required=True)
    first_name = graphene.String()
    last_name = graphene.String()


class ProfileSendInvitation(ExtensibleMutation):
    profile_user_roles = graphene.List(get_object_type_for_model(ProfileUserRole))
    emails_sent = graphene.Int()
    emails_held = graphene.Int(
        description="Invitations the project's pre-send hook held back for review."
    )

    class Input:
        profile_id = graphene.ID(required=True)
        emails = graphene.List(graphene.NonNull(graphene.String))
        invitees = graphene.List(
            graphene.NonNull(ProfileInviteeInput),
            description="Like `emails`, with the invitee's name to personalise the email.",
        )
        role = graphene.Field(ProfileRoleTypesEnum, required=True)
        message = graphene.String(description="A personal note included in the email.")

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileSendInvitation":
        validate_assignable_role(input.get("role"))

        profile_pk = get_pk_from_relay_id(input.get("profile_id"))
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
            raise _permission_error()

        invitees = [*(input.get("emails") or []), *(dict(i) for i in input.get("invitees") or [])]
        try:
            result = invitation_service.send_invitations(
                profile,
                invitees,
                role=input.get("role"),
                invited_by=info.context.user,
                message=input.get("message") or "",
                extra_fields=cls.extra_fields_from_input(info, input),
            )
        except ProfileMembershipError as error:
            raise as_graphql_error(error)

        return cls(
            profile_user_roles=result.invitations,
            emails_sent=result.emails_sent,
            emails_held=len(result.held),
        )


class ProfileAcceptInvitation(RelayMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))
    profile = graphene.Field(get_object_type_for_model(Profile))

    class Input:
        token = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileAcceptInvitation":
        try:
            invitation = invitation_service.accept_invitation(input.get("token"), info.context.user)
        except ProfileMembershipError as error:
            raise as_graphql_error(error)

        return ProfileAcceptInvitation(profile_user_role=invitation, profile=invitation.profile)


class ProfileAcceptInvitationWithSignup(RelayMutation):
    """
    Accept an invitation without an account: creates (or activates) the account for the
    invited email with the given password. Sign in with `email` and that password next.
    Only available when the project sets `BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED`.
    """

    success = graphene.Boolean()
    email = graphene.String(description="The email of the account to sign in with.")

    class Input:
        token = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String()
        last_name = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileAcceptInvitationWithSignup":
        try:
            invitation = invitation_service.accept_invitation_with_signup(
                input.get("token"),
                password=input.get("password"),
                first_name=input.get("first_name"),
                last_name=input.get("last_name"),
            )
        except ProfileMembershipError as error:
            raise as_graphql_error(error)

        return cls(success=True, email=invitation.invited_email)


class ProfileDeclineInvitation(RelayMutation):
    success = graphene.Boolean()

    class Input:
        token = graphene.String(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileDeclineInvitation":
        try:
            invitation_service.decline_invitation(input.get("token"), info.context.user)
        except ProfileMembershipError as error:
            raise as_graphql_error(error)

        return ProfileDeclineInvitation(success=True)


class ProfileCancelInvitation(RelayMutation):
    success = graphene.Boolean()
    profile_user_role = graphene.Field(
        get_object_type_for_model(ProfileUserRole),
        description="The cancelled invitation, or null when invitation history is off "
        "and the row was deleted.",
    )

    class Input:
        invitation_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileCancelInvitation":
        invitation = _get_invitation_by_id(input.get("invitation_id"))

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.delete_profileuserrole", invitation.profile
        ):
            raise _permission_error()

        try:
            invitation = invitation_service.cancel_invitation(invitation, by=info.context.user)
        except ProfileMembershipError as error:
            raise as_graphql_error(error)

        return ProfileCancelInvitation(
            success=True, profile_user_role=invitation if invitation.pk else None
        )


class ProfileResendInvitation(RelayMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))
    email_sent = graphene.Boolean()

    class Input:
        invitation_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileResendInvitation":
        invitation = _get_invitation_by_id(input.get("invitation_id"))

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", invitation.profile
        ):
            raise _permission_error()

        try:
            result = invitation_service.resend_invitation(invitation, by=info.context.user)
        except ProfileMembershipError as error:
            raise as_graphql_error(error)

        return ProfileResendInvitation(
            profile_user_role=result.invitations[0], email_sent=result.emails_sent > 0
        )
