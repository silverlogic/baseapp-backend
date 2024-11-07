from baseapp_auth.exceptions import UserPasswordExpiredException
from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


# TODO: Login is now handled by allAuth. Change Expired Password needs to be refactored
class LoginPasswordExpirationMixin:
    def check_password_expiration(self, user):
        if user.is_password_expired:
            raise UserPasswordExpiredException(user=user)


# TODO: Login is now handled by allAuth. Change Expired Password needs to be refactored
class LoginChangeExpiredPasswordRedirectSerializer(serializers.Serializer):
    redirect_url = serializers.URLField()
