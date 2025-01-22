from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.module_loading import import_string

from baseapp_auth.rest_framework.jwt.tokens import CustomClaimRefreshToken
from baseapp_auth.rest_framework.login.serializers import LoginPasswordExpirationMixin
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class CustomClaimSerializerMixin:
    _claim_serializer_class = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)

    @classmethod
    def get_claim_serializer_class(cls):
        try:
            return import_string(cls._claim_serializer_class)
        except ImportError as error:
            msg = "Could not import serializer '%s'" % cls._claim_serializer_class
            raise ImportError(msg) from error


class BaseJwtLoginSerializer(
    CustomClaimSerializerMixin, LoginPasswordExpirationMixin, TokenObtainPairSerializer
):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        if cls._claim_serializer_class:
            data = cls.get_claim_serializer_class()(user).data
            for key, value in data.items():
                token[key] = value

        return token

    def validate(self, data):
        validated_data = super().validate(data)
        self.check_password_expiration(self.user)
        return validated_data


class BaseJwtRefreshSerializer(CustomClaimSerializerMixin, TokenRefreshSerializer):
    _token_class = CustomClaimRefreshToken

    def token_class(cls, *args):
        return cls._token_class(*args, ClaimSerializerClass=cls.get_claim_serializer_class())


class LogoutDeviceSerializer(serializers.Serializer):
    device_id = serializers.CharField()

    def create(self, validated_data):
        from baseapp_devices.models import UserDevice

        device_id = validated_data.get("device_id")
        device = UserDevice.objects.filter(device_id=device_id).first()
        if not device:
            raise serializers.ValidationError({"device_id": "Device not found"})
        token = RefreshToken(device.device_token)
        token.blacklist()
        device.delete()
        return {"message": "Device logged out successfully"}
