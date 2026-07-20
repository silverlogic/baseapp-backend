import string
from typing import Any

import graphene
import swapper
from django.apps import apps
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
from baseapp_core.plugins import shared_services
from baseapp_profiles.utils import to_ascii_handle

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class BaseProfileSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    name = serializers.CharField(required=False)
    image = serializers.ImageField(required=False)
    banner_image = serializers.ImageField(required=False)
    url_path = serializers.SlugField(required=False)

    class Meta:
        model = Profile
        fields = ("owner", "name", "image", "banner_image", "biography", "url_path")

    def validate_url_path(self, value) -> str:
        if len(value) < 8:
            raise serializers.ValidationError(_("Username must be at least 8 characters long."))
        if value in string.punctuation:
            raise serializers.ValidationError(_("Username can only contain letters and numbers."))

        if apps.is_installed("baseapp_pages"):
            # Compare the *normalized* handle (ASCII-folded, as it will be stored)
            # against its collision-resolved form. It's only "already in use" when
            # collision resolution changes the path — not merely because normalization
            # reshaped the input (e.g. stripping the hyphen from "my-organization").
            normalized = f"/{to_ascii_handle(value)}"
            suggested_value = Profile.generate_url_path_str(value)
            if suggested_value and suggested_value != normalized:
                raise serializers.ValidationError(
                    _("Username already in use, suggested username: %(suggested_username)s")
                    % {"suggested_username": suggested_value},
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

    def create(self, validated_data) -> "Profile":
        url_path = validated_data.pop("url_path", None)
        instance = super().create(validated_data)
        if apps.is_installed("baseapp_pages") and url_path:
            instance.create_url_path(profile_name=url_path)
        return instance


class ProfileUpdateSerializer(BaseProfileSerializer):
    phone_number = serializers.CharField(required=False)
    image = serializers.ImageField(required=False, allow_null=True)
    banner_image = serializers.ImageField(required=False, allow_null=True)

    class Meta(BaseProfileSerializer.Meta):
        fields = BaseProfileSerializer.Meta.fields + ("phone_number",)

    def should_delete_field(self, data, field_name) -> bool:
        return field_name in data and not data[field_name]

    def update(self, instance, validated_data) -> "Profile":
        original_data = validated_data.copy()
        url_path = validated_data.pop("url_path", None)
        phone_number = validated_data.pop("phone_number", None)
        image = validated_data.pop("image", None)
        banner_image = validated_data.pop("banner_image", None)
        instance = super().update(instance, validated_data)
        if phone_number and hasattr(instance.owner, "phone_number"):
            instance.owner.phone_number = phone_number
            instance.owner.save(update_fields=["phone_number"])
        if apps.is_installed("baseapp_pages") and url_path:
            instance.url_paths.all().delete()
            instance.create_url_path(profile_name=url_path)
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
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileCreate":
        if not info.context.user.has_perm(f"{profile_app_label}.add_profile"):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        return super().mutate_and_get_payload(root, info, **input)

    @classmethod
    def perform_mutate(cls, serializer, info) -> "ProfileCreate":
        ProfileObjectType = Profile.get_graphql_object_type()
        # TODO: get target using get_obj_from_relay_id and inject into the serializer to be used
        # by validate and create methods
        obj = serializer.save()
        return cls(
            errors=None,
            profile=ProfileObjectType._meta.connection.Edge(node=obj),
        )


class ProfileUpdate(SerializerMutation):
    profile = graphene.Field(get_object_type_for_model(Profile))

    class Meta:
        serializer_class = ProfileUpdateSerializer

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    def get_serializer_kwargs(cls, root, info, id, **input) -> dict[str, Any]:
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
    def perform_mutate(cls, serializer, info) -> "ProfileUpdate":
        obj = serializer.save()
        return cls(
            errors=None,
            profile=obj,
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileUpdate":
        activity_name = "baseapp_profiles.update_profile"

        if service := shared_services.get("activity_log"):
            service.set_public_activity(verb=activity_name)

        return super().mutate_and_get_payload(root, info, **input)


class ProfileDelete(RelayMutation):
    deleted_id = graphene.ID()

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ProfileDelete":
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
