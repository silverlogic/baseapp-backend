from datetime import timedelta

from avatar.models import Avatar
from baseapp_auth.utils.referral_utils import get_user_referral_model, use_referrals
from baseapp_core.rest_framework.serializers import ModelSerializer
from baseapp_referrals.utils import get_referral_code, get_user_from_referral_code
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

User = get_user_model()

from baseapp_auth.password_validators import apply_password_validators
from baseapp_auth.tokens import ConfirmEmailTokenGenerator

from .fields import AvatarField


class UserBaseSerializer(ModelSerializer):
    avatar = AvatarField(required=False, allow_null=True)
    referral_code = serializers.SerializerMethodField()
    referred_by_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "is_email_verified",
            "new_email",
            "is_new_email_confirmed",
            "referral_code",
            "referred_by_code",
            "avatar",
            "first_name",
            "last_name",
        )
        private_fields = (
            "email",
            "is_email_verified",
            "new_email",
            "is_new_email_confirmed",
            "referral_code",
        )
        read_only_fields = (
            "email",
            "is_email_verified",
            "new_email",
            "is_new_email_confirmed",
        )

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
                Avatar.objects.create(user=instance, primary=True, avatar=avatar)
            else:
                instance.avatar_set.all().delete()

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


class ConfirmEmailSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, token):
        if not ConfirmEmailTokenGenerator().check_token(self.instance, token):
            raise serializers.ValidationError(_("Invalid token"))
        return token

    def update(self, instance, validated_data):
        instance.is_email_verified = True
        instance.save()
        return instance
