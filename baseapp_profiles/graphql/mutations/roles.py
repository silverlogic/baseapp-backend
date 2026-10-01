import logging

import graphene
import swapper
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_object_type_for_model,
    get_pk_from_relay_id,
    login_required,
)

from ..object_types import ProfileRoleTypesEnum

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_user_role_app_label = ProfileUserRole._meta.app_label

logger = logging.getLogger(__name__)


def validate_assignable_role(role: int) -> None:
    """
    Refuse a role the model will not accept.

    Every value a project declares reaches the API through `ProfileRoleTypesEnum`,
    including any it reserves for a later phase. Without this the write goes through to
    whatever constraint guards the column, and the caller gets an unhandled database
    error instead of being told the role is invalid.
    """
    if role not in ProfileUserRole.assignable_roles():
        raise GraphQLError(
            str(_("Invalid role type")),
            extensions={"code": "invalid_input"},
        )


class ProfileUserRoleCreate(RelayMutation):
    profile_user_roles = graphene.List(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        users_ids = graphene.List(graphene.ID)
        emails_to_invite = graphene.List(graphene.String)
        role_type = graphene.Field(ProfileRoleTypesEnum)

    @classmethod
    @login_required
    @transaction.atomic
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileUserRoleCreate":
        users_ids = input.get("users_ids")
        profile_id = input.get("profile_id")
        profile_pk = get_pk_from_relay_id(profile_id)
        role_type = input.get("role_type")
        emails_to_invite = input.get("emails_to_invite")
        try:
            profile = Profile.objects.get(pk=profile_pk)
        except Profile.DoesNotExist:
            raise GraphQLError(str(_("Profile not found")))

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )
        if not role_type:
            role_type = ProfileUserRole.ProfileRoles.MANAGER
        else:
            validate_assignable_role(role_type)

        # TODO on BA-2426: send invitation to new users emails
        if emails_to_invite:
            pass

        # De-duplicate the requested users, then reject any that are already members so the
        # client gets a clear message instead of a raw unique-constraint (IntegrityError).
        requested_user_pks = list(
            dict.fromkeys(get_pk_from_relay_id(user_id) for user_id in (users_ids or []))
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
                # Members added directly (rather than invited) are active immediately —
                # there is no acceptance step for them to go through. Without an explicit
                # status they would fall back to the field default of INACTIVE and reach
                # nothing, since an inactive membership grants no access.
                #
                # Saved one at a time rather than with bulk_create: bulk_create issues no
                # post_save, and consuming projects hang membership bookkeeping off that
                # signal. The loop is bounded by the members named in a single call and
                # already runs inside this transaction.
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

        return cls(
            errors=None,
            profile_user_roles=profile_user_roles,
        )


class ProfileUserRoleUpdate(RelayMutation):
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

        try:
            obj = ProfileUserRole.objects.get(user_id=user_pk, profile_id=profile_pk)
        except ProfileUserRole.DoesNotExist:
            raise GraphQLError(
                str(_("Role not found")),
                extensions={"code": "not_found"},
            )

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.change_profileuserrole", obj.profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        obj.role = role_type
        obj.save()

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
        try:
            obj = ProfileUserRole.objects.get(user_id=user_pk, profile_id=profile_pk)
        except ProfileUserRole.DoesNotExist:
            raise GraphQLError(
                str(_("User role not found")),
                extensions={"code": "not_found"},
            )

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.delete_profileuserrole", obj.profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        id_to_return = obj.relay_id
        obj.delete()

        return cls(deleted_id=id_to_return)
