from django.utils.translation import ugettext as _

from rest_framework import serializers

from apps.users.models import User


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate_email(self, email):
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(_('That email is already in use.  Choose another.'))
        return email

    def save(self):
        return User.objects.create_user(email=self.data['email'],
                                        password=self.data['password'])
