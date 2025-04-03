from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.signing import SignatureExpired
from django.utils.encoding import DjangoUnicodeDecodeError
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.authentication import JWTAuthentication

from baseapp_auth.password_validators import apply_password_validators

User = get_user_model()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, email):
        self.user = User.objects.filter(email=email).first()
        return email


class ResetPasswordBaseSerializer(serializers.Serializer):
    new_password = serializers.CharField()
    token = serializers.CharField()

    def validate_token(self, token):
        pass

    def validate_new_password(self, new_password):
        apply_password_validators(new_password)
        return new_password

    def save(self):
        self.user.set_password(self.data["new_password"])
        self.user.save()


class ResetPasswordSerializer(ResetPasswordBaseSerializer):
    def validate_token(self, token):
        try:
            decoded_token = urlsafe_base64_decode(token)
            user_id, user_token = signing.loads(decoded_token.decode())
            self.user = user = User.objects.get(pk=user_id)
            if not (default_token_generator.check_token(user, user_token)):
                raise serializers.ValidationError(_("Invalid token."))
        except (
            signing.BadSignature,
            DjangoUnicodeDecodeError,
            SignatureExpired,
            UnicodeDecodeError,
        ):
            raise serializers.ValidationError(_("Invalid token."))
        return token


class ResetPasswordJwtSerializer(ResetPasswordBaseSerializer):
    def validate_token(self, token):
        authenticator = JWTAuthentication()
        validated_token = authenticator.get_validated_token(token)
        self.user = authenticator.get_user(validated_token)
        return token
