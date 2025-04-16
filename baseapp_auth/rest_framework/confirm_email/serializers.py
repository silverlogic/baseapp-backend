from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_auth.tokens import ConfirmEmailTokenGenerator


class ConfirmEmailSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, token):
        try:
            if not ConfirmEmailTokenGenerator().check_token(self.instance, token):
                raise serializers.ValidationError(_("Invalid token."))
            return token
        except ValueError:
            raise serializers.ValidationError(_("Invalid token."))

    def update(self, instance, validated_data):
        instance.is_email_verified = True
        instance.save()
        return instance
