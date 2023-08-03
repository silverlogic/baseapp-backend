from baseapp_auth.rest_framework.login.serializers import LoginPasswordExpirationMixin
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class BaseJwtLoginSerializer(LoginPasswordExpirationMixin, TokenObtainPairSerializer):
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

    def validate(self, data):
        validated_data = super().validate(data)
        self.check_password_expiration(self.user)
        return validated_data
