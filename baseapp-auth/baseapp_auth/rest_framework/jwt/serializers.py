from django.contrib.auth import authenticate, get_user_model
from django.utils.translation import gettext_lazy as _

from rest_framework import exceptions, serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from baseapp_auth.rest_framework.login.serializers import LoginSerializer


class BaseJwtLoginSerializer(TokenObtainPairSerializer):
    claim_serializer_class = None

    @classmethod
    def get_claim_serializer(cls, user):
        if cls.claim_serializer_class:
            return cls.claim_serializer_class(user)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        claim_serializer = cls.get_claim_serializer(user)
        if claim_serializer:
            data = cls.get_claim_serializer(user).data
            for key, value in data.items():
                token[key] = value

        return token

    def validate_email(self, email):
        User = get_user_model()
        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise exceptions.ValidationError(_("Email does not exist."))
        return email

    def validate(self, data):
        self.validate_email(data["email"])
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
        return super().validate(data)
