from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.module_loading import import_string
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)

if TYPE_CHECKING:
    from rest_framework.serializers import Serializer
    from rest_framework_simplejwt.tokens import RefreshToken

from baseapp_auth.rest_framework.jwt.tokens import CustomClaimRefreshToken
from baseapp_auth.rest_framework.login.serializers import LoginPasswordExpirationMixin

User = get_user_model()


class CustomClaimSerializerMixin:
    _claim_serializer_class = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)

    @classmethod
    def get_claim_serializer_class(cls) -> "type[Serializer]":
        try:
            return import_string(cls._claim_serializer_class)
        except ImportError:
            msg = "Could not import serializer '%s'" % cls._claim_serializer_class
            raise ImportError(msg)


class BaseJwtLoginSerializer(
    CustomClaimSerializerMixin, LoginPasswordExpirationMixin, TokenObtainPairSerializer
):
    @classmethod
    def get_token(cls, user) -> "RefreshToken":
        token = super().get_token(user)

        # Add custom claims
        if cls._claim_serializer_class:
            data = cls.get_claim_serializer_class()(user).data
            for key, value in data.items():
                token[key] = value

        return token

    def validate(self, data) -> dict[str, Any]:
        validated_data = super().validate(data)
        self.check_password_expiration(self.user)
        return validated_data


class BaseJwtRefreshSerializer(CustomClaimSerializerMixin, TokenRefreshSerializer):
    _token_class = CustomClaimRefreshToken

    def token_class(cls, *args) -> CustomClaimRefreshToken:
        return cls._token_class(*args, ClaimSerializerClass=cls.get_claim_serializer_class())
