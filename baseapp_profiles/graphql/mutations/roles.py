import logging

import graphene
import swapper
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_object_type_for_model,
    get_pk_from_relay_id,
    login_required,
)
from baseapp_profiles.conf import keep_invitation_history
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as invitation_service
from baseapp_profiles.services import members as member_service

from ..object_types import ProfileRoleTypesEnum
from .base import ExtensibleMutation

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_user_role_app_label = ProfileUserRole._meta.app_label
User = get_user_model()

logger = logging.getLogger(__name__)


def validate_assignable_role(role: int) -> None:
    """
    Refuse a role the model will not accept.

    Every value a project declares reaches the API through `ProfileRoleTypesEnum`,
    including any it reserves for a later phase. Without this the write goes through to
    whatever constraint guards the column, and the caller gets an unhandled database
    error instead of being told the role is invalid.
    """
    try:
        member_service.validate_role(role)
    except ProfileMembershipError as error:
        raise GraphQLError(error.message, extensions={"code": error.code})


def get_membership(profile_pk: int | str, user_pk: int | str) -> "ProfileUserRole | None":
    """
    The user's row on the profile: the open one (member or pending invite).

    Without invitation history a person has a single row, so their declined or expired
    invitation is returned when there is no open one, as before. With history on, closed
    rows are a record and never the target of these mutations.
    """
    rows = ProfileUserRole.objects.select_related("profile").filter(
        profile_id=profile_pk, user_id=user_pk
    )
    if keep_invitation_history():
        return rows.open().first()
    return rows.open().first() or rows.order_by("-pk").first()


def _permission_error() -> GraphQLError:
    return GraphQLError(
        str(_("You don't have permission to perform this action")),
        extensions={"code": "permission_required"},
    )


class ProfileUserRoleCreate(ExtensibleMutation):
    """Add existing users to a profile as ACTIVE members, without an invitation."""

    profile_user_roles = graphene.List(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        users_ids = graphene.List(graphene.ID)
        emails_to_invite = graphene.List(graphene.String)
        role_type = graphene.Field(ProfileRoleTypesEnum)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileUserRoleCreate":
        profile_pk = get_pk_from_relay_id(input.get("profile_id"))
        role_type = input.get("role_type")
        try:
            profile = Profile.objects.get(pk=profile_pk)
        except Profile.DoesNotExist:
            raise GraphQLError(str(_("Profile not found")))

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", profile
        ):
            raise _permission_error()
        if role_type:
            validate_assignable_role(role_type)

        # TODO on BA-2426: send invitation to new users emails
        # (`profileSendInvitation` invites by email.)

        user_pks = list(
            dict.fromkeys(
                str(get_pk_from_relay_id(user_id)) for user_id in input.get("users_ids") or []
            )
        )
        users_by_pk = {
            str(pk): user for pk, user in User._default_manager.in_bulk(user_pks).items()
        }
        if len(users_by_pk) != len(user_pks):
            raise GraphQLError(str(_("User not found")), extensions={"code": "not_found"})

        try:
            profile_user_roles = member_service.add_members(
                profile,
                [users_by_pk[pk] for pk in user_pks],
                role=role_type or None,
                by=info.context.user,
                extra_fields=cls.extra_fields_from_input(info, input),
            )
        except ProfileMembershipError as error:
            raise GraphQLError(error.message, extensions={"code": error.code})

        return cls(errors=None, profile_user_roles=profile_user_roles)


class ProfileUserRoleUpdate(ExtensibleMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)
        role_type = graphene.Field(ProfileRoleTypesEnum, required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileUserRoleUpdate":
        user_id = input.get("user_id")
        profile_id = input.get("profile_id")
        role_type = input.get("role_type")
        if role_type is None:
            raise GraphQLError(
                str(_("Role is required")),
                extensions={"code": "invalid_input"},
            )
        validate_assignable_role(role_type)
        user_pk = get_pk_from_relay_id(user_id)
        profile_pk = get_pk_from_relay_id(profile_id)

        obj = get_membership(profile_pk, user_pk)
        if obj is None:
            raise GraphQLError(
                str(_("Role not found")),
                extensions={"code": "not_found"},
            )

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.change_profileuserrole", obj.profile
        ):
            raise _permission_error()

        try:
            obj = member_service.update_member(
                obj,
                role=role_type,
                by=info.context.user,
                extra_fields=cls.extra_fields_from_input(info, input),
            )
        except ProfileMembershipError as error:
            raise GraphQLError(error.message, extensions={"code": error.code})

        return cls(profile_user_role=obj)


class ProfileUserRoleDelete(RelayMutation):
    deleted_id = graphene.ID()

    class Input:
        profile_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileUserRoleDelete":
        profile_id = input.get("profile_id")
        user_id = input.get("user_id")
        profile_pk = get_pk_from_relay_id(profile_id)
        user_pk = get_pk_from_relay_id(user_id)
        obj = get_membership(profile_pk, user_pk)
        if obj is None:
            raise GraphQLError(
                str(_("User role not found")),
                extensions={"code": "not_found"},
            )

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.delete_profileuserrole", obj.profile
        ):
            raise _permission_error()

        id_to_return = obj.relay_id
        try:
            if obj.status == ProfileUserRole.ProfileRoleStatus.PENDING:
                # Removing someone who has not accepted yet withdraws their invitation, so
                # it is kept as CANCELLED when history is on.
                invitation_service.cancel_invitation(obj, by=info.context.user)
            else:
                member_service.remove_member(obj, by=info.context.user)
        except ProfileMembershipError as error:
            raise GraphQLError(error.message, extensions={"code": error.code})

        return cls(deleted_id=id_to_return)


def _change_member_status(info, input: dict, apply) -> "ProfileUserRole":
    """Shared body of the deactivate and reactivate mutations."""
    obj = get_membership(
        get_pk_from_relay_id(input.get("profile_id")),
        get_pk_from_relay_id(input.get("user_id")),
    )
    if obj is None:
        raise GraphQLError(
            str(_("Role not found")),
            extensions={"code": "not_found"},
        )

    if not info.context.user.has_perm(
        f"{profile_user_role_app_label}.change_profileuserrole", obj.profile
    ):
        raise _permission_error()

    try:
        return apply(obj, by=info.context.user)
    except ProfileMembershipError as error:
        raise GraphQLError(error.message, extensions={"code": error.code})


class ProfileMemberDeactivate(ExtensibleMutation):
    """Deactivate a member: they keep their row but lose access until reactivated."""

    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)
        reason = graphene.String(
            description="Why the member is deactivated. Passed to the `member_deactivated` "
            "signal; not stored by BaseApp."
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileMemberDeactivate":
        def deactivate(membership: "ProfileUserRole", by) -> "ProfileUserRole":
            return member_service.deactivate_member(
                membership,
                by=by,
                reason=input.get("reason") or "",
                extra_fields=cls.extra_fields_from_input(info, input),
            )

        obj = _change_member_status(info, input, deactivate)
        return cls(profile_user_role=obj)


class ProfileMemberReactivate(RelayMutation):
    """Give a deactivated member their access back."""

    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileMemberReactivate":
        obj = _change_member_status(info, input, member_service.reactivate_member)
        return cls(profile_user_role=obj)
