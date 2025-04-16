from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_auth.exceptions import UserPasswordExpiredException
from baseapp_auth.password_validators import apply_password_validators
from baseapp_auth.rest_framework.login.serializers import LoginSerializer

User = get_user_model()

from baseapp_auth.tokens import ChangeExpiredPasswordTokenGenerator


class ChangeExpiredPasswordSerializer(serializers.Serializer):
    user: Optional[AbstractUser] = None

    current_password = serializers.CharField()
    new_password = serializers.CharField()
    token = serializers.CharField()

    def validate_new_password(self, new_password):
        apply_password_validators(new_password)
        return new_password

    def validate_token(self, token):
        generator = ChangeExpiredPasswordTokenGenerator()
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

    def save(self, *args, **kwargs):
        current_password = self.validated_data["current_password"]
        new_password = self.validated_data["new_password"]
        if current_password == new_password:
            raise serializers.ValidationError(
                dict(new_password=[_("New password cannot be the same as the current password.")])
            )
        try:
            # Make sure the current password is correct
            login_serializer = LoginSerializer(
                data=dict(email=self.user.email, password=current_password)
            )
            login_serializer.is_valid(raise_exception=True)
        except UserPasswordExpiredException:
            pass
        self.user.set_password(self.data["new_password"])
        self.user.save()
