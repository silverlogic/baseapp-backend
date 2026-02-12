import string
from datetime import timedelta

import graphene
import swapper
from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from rest_framework import serializers

from baseapp_core.graphql import (
    RelayMutation,
    SerializerMutation,
    get_object_type_for_model,
    get_pk_from_relay_id,
    login_required,
)
from baseapp_pages.models import URLPath
from baseapp_profiles.constants import INVITATION_EXPIRATION_DAYS

from .object_types import ProfileRoleTypesEnum

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_user_role_app_label = ProfileUserRole._meta.app_label
User = swapper.load_model("users", "User")


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


class BaseProfileSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    name = serializers.CharField(required=False)
    image = serializers.ImageField(required=False)
    banner_image = serializers.ImageField(required=False)
    url_path = serializers.SlugField(required=False)

    class Meta:
        model = Profile
        fields = ("owner", "name", "image", "banner_image", "biography", "url_path")

    def validate_url_path(self, value):
        if len(value) < 8:
            raise serializers.ValidationError(_("Username must be at least 8 characters long."))
        if value in string.punctuation:
            raise serializers.ValidationError(_("Username can only contain letters and numbers."))
        value_with_slash = value if value.startswith("/") else f"/{value}"
        if URLPath.objects.filter(path=value_with_slash).exists():
            suggested_value = self.instance.generate_url_path(increase_path_string=value)
            raise serializers.ValidationError(
                _(f"Username already in use, suggested username: {suggested_value}"),
            )

        return value


class ProfileCreateSerializer(BaseProfileSerializer):
    name = serializers.CharField(required=True)
    target = serializers.CharField(required=False)

    class Meta(BaseProfileSerializer.Meta):
        fields = BaseProfileSerializer.Meta.fields + (
            "target",
            "target_content_type",
            "target_object_id",
        )

    def create(self, validated_data):
        url_path = validated_data.pop("url_path", None)
        instance = super().create(validated_data)
        if url_path:
            URLPath.objects.create(path=url_path, target=instance, is_active=True)
        return instance


class ProfileUpdateSerializer(BaseProfileSerializer):
    phone_number = serializers.CharField(required=False)
    image = serializers.ImageField(required=False, allow_null=True)
    banner_image = serializers.ImageField(required=False, allow_null=True)

    class Meta(BaseProfileSerializer.Meta):
        fields = BaseProfileSerializer.Meta.fields + ("phone_number",)

    def should_delete_field(self, data, field_name):
        return field_name in data and not data[field_name]

    def update(self, instance, validated_data):
        original_data = validated_data.copy()
        url_path = validated_data.pop("url_path", None)
        phone_number = validated_data.pop("phone_number", None)
        image = validated_data.pop("image", None)
        banner_image = validated_data.pop("banner_image", None)
        instance = super().update(instance, validated_data)
        if phone_number and hasattr(instance.owner, "phone_number"):
            instance.owner.phone_number = phone_number
            instance.owner.save(update_fields=["phone_number"])
        if url_path:
            instance.url_paths.all().delete()
            path_with_slash = url_path if url_path.startswith("/") else f"/{url_path}"
            URLPath.objects.create(path=path_with_slash, target=instance, is_active=True)
        if self.should_delete_field(original_data, "image"):
            instance.image.delete()
        elif "image" in original_data:
            super().update(instance, {"image": image})
        if self.should_delete_field(original_data, "banner_image"):
            instance.banner_image.delete()
        elif "banner_image" in original_data:
            super().update(instance, {"banner_image": banner_image})
        return instance


class ProfileCreate(SerializerMutation):
    profile = graphene.Field(lambda: Profile.get_graphql_object_type()._meta.connection.Edge)

    class Meta:
        serializer_class = ProfileCreateSerializer

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        if not info.context.user.has_perm(f"{profile_app_label}.add_profile"):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        return super().mutate_and_get_payload(root, info, **input)

    @classmethod
    def perform_mutate(cls, serializer, info):
        ProfileObjectType = Profile.get_graphql_object_type()
        # TODO: get target using get_obj_from_relay_id and inject into the serializer to be used
        # by validate and create methods
        obj = serializer.save()
        return cls(
            errors=None,
            profile=ProfileObjectType._meta.connection.Edge(node=obj),
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
    def mutate_and_get_payload(cls, root, info, **input):
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
        elif role_type and role_type not in ProfileUserRole.ProfileRoles.values:
            raise GraphQLError(str(_("Invalid role type")))

        # TODO on BA-2426: send invitation to new users emails
        if emails_to_invite:
            pass

        profile_user_roles = [
            ProfileUserRole(
                user_id=get_pk_from_relay_id(user_id), profile_id=profile_pk, role=role_type
            )
            for user_id in users_ids
        ]
        profile_user_roles = ProfileUserRole.objects.bulk_create(profile_user_roles)

        # TODO on BA-2426: send invitation to existing users

        return cls(
            errors=None,
            profile_user_roles=profile_user_roles,
        )


class ProfileUserRoleUpdate(RelayMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)
        role_type = graphene.Field(ProfileRoleTypesEnum)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        user_id = input.get("user_id")
        profile_id = input.get("profile_id")
        role_type = input.get("role_type")
        user_pk = get_pk_from_relay_id(user_id)
        profile_pk = get_pk_from_relay_id(profile_id)

        try:
            obj = ProfileUserRole.objects.get(user_id=user_pk, profile_id=profile_pk)
        except ProfileUserRole.DoesNotExist:
            raise GraphQLError(str(_("Role not found")))

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
    def mutate_and_get_payload(cls, root, info, **input):
        profile_id = input.get("profile_id")
        user_id = input.get("user_id")
        profile_pk = get_pk_from_relay_id(profile_id)
        user_pk = get_pk_from_relay_id(user_id)
        obj = ProfileUserRole.objects.get(user_id=user_pk, profile_id=profile_pk)

        if not obj:
            raise GraphQLError(str(_("User role not found")))

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


class ProfileUpdate(SerializerMutation):
    profile = graphene.Field(get_object_type_for_model(Profile))

    class Meta:
        serializer_class = ProfileUpdateSerializer

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    def get_serializer_kwargs(cls, root, info, id, **input):
        kwargs = super().get_serializer_kwargs(root, info, **input)
        input = kwargs["data"]

        try:
            pk = get_pk_from_relay_id(id)
            instance = Profile.objects.get(pk=pk)
        except Profile.DoesNotExist:
            raise ValueError(str(_("Profile not found")))

        if not info.context.user.has_perm(f"{profile_app_label}.change_profile", instance):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        return {
            "instance": instance,
            "data": input,
            "partial": True,
            "context": {"request": info.context},
        }

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(
            errors=None,
            profile=obj,
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        activity_name = "baseapp_profiles.update_profile"

        if apps.is_installed("baseapp.activity_log"):
            from baseapp.activity_log.context import set_public_activity

            set_public_activity(verb=activity_name)

        return super().mutate_and_get_payload(root, info, **input)


class ProfileDelete(RelayMutation):
    deleted_id = graphene.ID()

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        relay_id = input.get("id")
        pk = get_pk_from_relay_id(relay_id)

        try:
            obj = Profile.objects.get(pk=pk)
        except Profile.DoesNotExist:
            obj = None

        error_exception = GraphQLError(
            str(_("You don't have permission to perform this action")),
            extensions={"code": "permission_required"},
        )
        if not obj:
            raise error_exception

        if not info.context.user.has_perm(f"{profile_app_label}.delete_profile", obj):
            raise error_exception

        obj.delete()

        return cls(deleted_id=relay_id)


class ProfileSendInvitation(RelayMutation):
    profile_user_role = graphene.Field(get_object_type_for_model(ProfileUserRole))

    class Input:
        profile_id = graphene.ID(required=True)
        email = graphene.String(required=True)
        role = graphene.Field(ProfileRoleTypesEnum, required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        from django.contrib.auth import get_user_model

        from baseapp_profiles.emails import send_invitation_email

        profile_id = input.get("profile_id")
        email = input.get("email")
        role = input.get("role")

        profile_pk = get_pk_from_relay_id(profile_id)
        profile = Profile.objects.get(pk=profile_pk)

        if not info.context.user.has_perm(
            f"{profile_user_role_app_label}.add_profileuserrole", profile
        ):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        normalized_email = email.lower()
        User = get_user_model()

        # Lookup invited user if they exist
        try:
            invited_user = User.objects.get(email__iexact=normalized_email)
        except User.DoesNotExist:
            invited_user = None

        # Use transaction with select_for_update to prevent race conditions
        with transaction.atomic():
            existing_role = (
                ProfileUserRole.objects.select_for_update()
                .filter(profile=profile, invited_email__iexact=normalized_email)
                .first()
            )

            if existing_role:
                if existing_role.status == ProfileUserRole.ProfileRoleStatus.ACTIVE:
                    raise GraphQLError(
                        str(_("This user is already a member of this profile")),
                        extensions={"code": "already_member"},
                    )

                if existing_role.status == ProfileUserRole.ProfileRoleStatus.PENDING:
                    if not existing_role.is_invitation_expired():
                        raise GraphQLError(
                            str(_("An invitation has already been sent to this email")),
                            extensions={"code": "duplicate_invitation"},
                        )
                    # Expired PENDING invitation: update in place
                    existing_role.status = ProfileUserRole.ProfileRoleStatus.EXPIRED

                # DECLINED, INACTIVE, or EXPIRED: reuse existing row
                if existing_role.status in [
                    ProfileUserRole.ProfileRoleStatus.DECLINED,
                    ProfileUserRole.ProfileRoleStatus.INACTIVE,
                    ProfileUserRole.ProfileRoleStatus.EXPIRED,
                ]:
                    _reset_invitation_for_send(existing_role, role=role, user=invited_user)
                    existing_role.save()
                    invitation = existing_role
                else:
                    # Should not reach here, but safety fallback
                    raise GraphQLError(
                        str(_("Cannot send invitation in current state")),
                        extensions={"code": "invalid_status"},
                    )
            else:
                # No existing role: create new invitation
                try:
                    invitation = ProfileUserRole.objects.create(
                        profile=profile,
                        user=invited_user,
                        invited_email=normalized_email,
                        role=role,
                        status=ProfileUserRole.ProfileRoleStatus.PENDING,
                        invited_at=timezone.now(),
                        invitation_expires_at=(
                            timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS)
                        ),
                    )
                    invitation.generate_invitation_token()
                    invitation.save()
                except IntegrityError:
                    # Race condition: another request created the row first.
                    # Re-fetch and return duplicate_invitation error.
                    raise GraphQLError(
                        str(_("An invitation has already been sent to this email")),
                        extensions={"code": "duplicate_invitation"},
                    )

        send_invitation_email(invitation, info.context.user)

        return ProfileSendInvitation(profile_user_role=invitation)


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

        send_invitation_email(invitation, info.context.user)

        return ProfileResendInvitation(profile_user_role=invitation)


class ProfilesMutations(object):
    profile_create = ProfileCreate.Field()
    profile_update = ProfileUpdate.Field()
    profile_delete = ProfileDelete.Field()
    profile_user_role_create = ProfileUserRoleCreate.Field()
    profile_user_role_update = ProfileUserRoleUpdate.Field()
    profile_user_role_delete = ProfileUserRoleDelete.Field()
    profile_send_invitation = ProfileSendInvitation.Field()
    profile_accept_invitation = ProfileAcceptInvitation.Field()
    profile_decline_invitation = ProfileDeclineInvitation.Field()
    profile_cancel_invitation = ProfileCancelInvitation.Field()
    profile_resend_invitation = ProfileResendInvitation.Field()
