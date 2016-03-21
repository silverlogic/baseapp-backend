from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.authtoken.models import Token

from apps.users.models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate_email(self, email):
        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(_('Email does not exist.'))
        return email

    def validate(self, data):
        if not self.user.check_password(data['password']):
            raise serializers.ValidationError({'password': _('Incorrect password.')})
        return data

    def create(self, validated_data):
        return Token.objects.get_or_create(user=self.user)[0]
