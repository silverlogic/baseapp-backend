from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken

from baseapp_auth.tokens import PreAuthTokenGenerator

User = get_user_model()


class AuthTokenPreAuthSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, token):
        generator = PreAuthTokenGenerator()
        value = generator.decode_token(token)
        if value is None:
            raise serializers.ValidationError(_("Invalid token."))
        try:
            self.user = User.objects.get(id=value[0])
        except User.DoesNotExist:
            raise serializers.ValidationError(_("Invalid token."))
        if not generator.is_value_valid(self.user, value):
            raise serializers.ValidationError(_("Invalid token."))
        return token

    def save(self):
        return Token.objects.get_or_create(user=self.user)[0]


class JWTPreAuthSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, token):
        generator = PreAuthTokenGenerator()
        value = generator.decode_token(token)
        if value is None:
            raise serializers.ValidationError(_("Invalid token."))
        try:
            self.user = User.objects.get(id=value[0])
        except User.DoesNotExist:
            raise serializers.ValidationError(_("Invalid token."))
        if not generator.is_value_valid(self.user, value):
            raise serializers.ValidationError(_("Invalid token."))
        return token

    def save(self):
        return RefreshToken.for_user(self.user)
