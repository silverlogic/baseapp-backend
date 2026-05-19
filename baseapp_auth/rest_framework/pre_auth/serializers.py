from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken

from baseapp_auth.tokens import PreAuthTokenGenerator

User = get_user_model()

_INVALID_TOKEN_ERROR = {"non_field_errors": [_("Invalid token.")]}


class BasePreAuthSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, token: str) -> str:
        """Validate the pre-auth token and bind the resolved user to self.user."""
        generator = PreAuthTokenGenerator()
        value = generator.decode_token(token)
        if value is None:
            raise serializers.ValidationError(_INVALID_TOKEN_ERROR)
        try:
            self.user = User.objects.get(id=value[0])
        except User.DoesNotExist:
            raise serializers.ValidationError(_INVALID_TOKEN_ERROR) from None
        if not generator.is_value_valid(self.user, value):
            raise serializers.ValidationError(_INVALID_TOKEN_ERROR)
        return token


class AuthTokenPreAuthSerializer(BasePreAuthSerializer):
    def save(self) -> Token:
        return Token.objects.get_or_create(user=self.user)[0]


class JWTPreAuthSerializer(BasePreAuthSerializer):
    def save(self) -> RefreshToken:
        return RefreshToken.for_user(self.user)
