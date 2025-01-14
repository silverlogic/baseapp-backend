from baseapp_auth.exceptions import UserPasswordExpiredException
from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


# TODO: MFA Follow Up | Expired Password Refactor
class LoginPasswordExpirationMixin:
    def check_password_expiration(self, user):
        if user.is_password_expired:
            raise UserPasswordExpiredException(user=user)


# TODO: MFA Follow Up | Expired Password Refactor
class LoginChangeExpiredPasswordRedirectSerializer(serializers.Serializer):
    redirect_url = serializers.URLField()
