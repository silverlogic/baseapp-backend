from datetime import timedelta

import swapper
from constance import config
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_auth.utils.referral_utils import get_user_referral_model, use_referrals
from baseapp_core.graphql import get_obj_relay_id
from baseapp_core.rest_framework.fields import ThumbnailImageField
from baseapp_core.rest_framework.serializers import ModelSerializer
from baseapp_referrals.utils import get_referral_code, get_user_from_referral_code

from .fields import AvatarField

User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")

from baseapp_auth.password_validators import apply_password_validators


class JWTProfileSerializer(serializers.ModelSerializer):
    """
    Serializes minimal profile data that will be attached to the JWT token as claim
    """

    id = serializers.SerializerMethodField()
    url_path = serializers.SerializerMethodField()
    image = ThumbnailImageField(required=False, sizes={"small": (100, 100)})

    class Meta:
        model = Profile
        fields = ("id", "name", "image", "url_path")

    def get_id(self, profile):
        return get_obj_relay_id(profile)

    def get_url_path(self, profile):
        path_obj = getattr(profile, "url_path", None)
        return getattr(path_obj, "path", None)

    def to_representation(self, profile):
        data = super().to_representation(profile)
        if data["image"] is not None:
            data["image"] = data["image"]["small"]
        return data


class UserBaseSerializer(ModelSerializer):
    profile = JWTProfileSerializer(read_only=True)
    avatar = AvatarField(required=False, allow_null=True, write_only=True)
    email_verification_required = serializers.SerializerMethodField()
    referral_code = serializers.SerializerMethodField()
    referred_by_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "avatar",
            "profile",
            "email",
            "is_email_verified",
            "email_verification_required",
            "new_email",
            "is_new_email_confirmed",
            "referral_code",
            "referred_by_code",
            "phone_number",
            "preferred_language",
        )
        private_fields = (
            "email",
            "is_email_verified",
            "email_verification_required",
            "new_email",
            "is_new_email_confirmed",
            "referral_code",
            "preferred_language",
        )
        read_only_fields = (
            "email",
            "is_email_verified",
            "email_verification_required",
            "new_email",
            "is_new_email_confirmed",
        )

    def get_email_verification_required(self, user):
        return config.EMAIL_VERIFICATION_REQUIRED

    def get_referral_code(self, user):
        if use_referrals():
            return get_referral_code(user)
        return ""


class UserSerializer(UserBaseSerializer):
    class Meta(UserBaseSerializer.Meta):
        pass

    def validate_referred_by_code(self, referred_by_code):
        if use_referrals() and referred_by_code:
            self.referrer = get_user_from_referral_code(referred_by_code)
            if not self.referrer:
                raise serializers.ValidationError(_("Invalid referral code."))
            elif self.referrer == self.instance:
                raise serializers.ValidationError(_("You cannot refer yourself."))
            elif (timezone.now() - self.instance.date_joined) > timedelta(days=1):
                raise serializers.ValidationError(
                    _("You are no longer allowed to change who you were referred by.")
                )
            elif hasattr(self.instance, "referred_by"):
                raise serializers.ValidationError(_("You have already been referred by somebody."))
        return referred_by_code

    def update(self, instance, validated_data):
        if use_referrals() and hasattr(self, "referrer"):
            get_user_referral_model().objects.create(referrer=self.referrer, referee=instance)

        if "avatar" in validated_data:
            avatar = validated_data.pop("avatar")
            if avatar:
                instance.profile.image = avatar
            else:
                instance.profile.image = None
            instance.profile.save(update_fields=["image"])

        return super().update(instance, validated_data)

    def to_representation(self, user):
        request = self.context["request"]
        if request.user.is_authenticated and request.user.pk == user.pk:
            return super().to_representation(user)
        else:
            return UserPublicSerializer(user, context=self.context).data


class UserPublicSerializer(UserBaseSerializer):
    class Meta(UserSerializer.Meta):
        fields = tuple(set(UserSerializer.Meta.fields) - set(UserSerializer.Meta.private_fields))
        read_only_fields = tuple(
            set(UserSerializer.Meta.read_only_fields) - set(UserSerializer.Meta.private_fields)
        )


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_current_password(self, current_password):
        user = self.context["request"].user
        if not user.check_password(current_password):
            raise serializers.ValidationError(_("That is not your current password."))
        return current_password

    def validate_new_password(self, new_password):
        apply_password_validators(new_password)
        return new_password

    def save(self):
        user = self.context["request"].user
        user.set_password(self.data["new_password"])
        user.save()


class UserPermissionSerializer(serializers.Serializer):
    perm = serializers.CharField(required=True)


class UserContentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentType
        fields = ["app_label", "model"]


class UserManagePermissionSerializer(serializers.ModelSerializer):
    content_type = UserContentTypeSerializer(read_only=True)
    permissions = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )

    class Meta:
        model = Permission
        fields = ["id", "codename", "content_type", "permissions"]
        extra_kwargs = {
            "codename": {"required": False},
        }

    def create(self, validated_data):
        user = self.context["user"]
        if not user:
            raise serializers.ValidationError({"user": _("User does not exist.")})
        if not self.context["request"].user.has_perm("users.change_user"):
            raise serializers.ValidationError(
                {"detail": _("You do not have permission to perform this action.")}
            )
        perms = validated_data.pop("permissions", [])
        if len(perms) > 0:
            permissions = Permission.objects.filter(codename__in=perms)
            user.user_permissions.set(permissions)

        if validated_data.get("codename"):
            permission = Permission.objects.filter(codename=validated_data["codename"]).first()
            if not permission:
                raise serializers.ValidationError(
                    {"codename": _("Permission with this codename does not exist.")}
                )
            user.user_permissions.add(permission)
            return permission
        return validated_data
