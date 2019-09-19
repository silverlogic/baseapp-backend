from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.signing import SignatureExpired
from django.utils.encoding import DjangoUnicodeDecodeError
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from apps.users.models import User


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, email):
        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(_("Email does not exist."))
        return email


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField()
    token = serializers.CharField()

    def validate_token(self, token):
        try:
            decoded_token = urlsafe_base64_decode(token)
            user_id, user_token = signing.loads(decoded_token)
            self.user = user = User.objects.get(pk=user_id)
            if not (default_token_generator.check_token(user, user_token)):
                raise serializers.ValidationError(_("Invalid token."))
        except (signing.BadSignature, DjangoUnicodeDecodeError, SignatureExpired):
            raise serializers.ValidationError(_("Invalid token."))
        return token

    def save(self):
        self.user.set_password(self.data["new_password"])
        self.user.save()
