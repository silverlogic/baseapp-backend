from baseapp_auth.rest_framework.login.serializers import LoginPasswordExpirationMixin
from django.contrib.auth import get_user_model
from django.utils.module_loading import import_string
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class BaseJwtLoginSerializer(LoginPasswordExpirationMixin, TokenObtainPairSerializer):
    _claim_serializer_class = ""

    @classmethod
    def get_claim_serializer_class(cls):
        try:
            return import_string(cls._claim_serializer_class)
        except ImportError:
            msg = "Could not import serializer '%s'" % cls._claim_serializer_class
            raise ImportError(msg)

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
