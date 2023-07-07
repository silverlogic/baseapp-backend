from django.utils.translation import gettext_lazy as _

from rest_framework import exceptions, serializers
from rest_framework.authtoken.models import Token

from baseapp_auth.models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate_email(self, email):
        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise exceptions.ValidationError(_("Email does not exist."))
        return email

    def validate(self, data):
        if not self.user.check_password(data["password"]):
            raise exceptions.ValidationError({"password": _("Incorrect password.")})
        if self.user.is_password_expired:
            raise exceptions.AuthenticationFailed(
                {
                    "password": [
                        _(
                            "Your password has expired. Please reset it or contact the administrator."
                        )
                    ]
                }
            )
        return data

    def create(self, validated_data):
        return Token.objects.get_or_create(user=self.user)[0]
