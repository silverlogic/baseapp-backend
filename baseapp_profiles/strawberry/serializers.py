import string

import swapper
from django.apps import apps
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_profiles.utils import to_ascii_handle

Profile = swapper.load_model("baseapp_profiles", "Profile")


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
