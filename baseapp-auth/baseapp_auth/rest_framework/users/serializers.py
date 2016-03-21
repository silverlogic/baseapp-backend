from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'is_email_verified', 'new_email', 'is_new_email_verified')


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_current_password(self, current_password):
        user = self.context['request'].user
        if not user.check_password(current_password):
            raise serializers.ValidationError(_('That is not your current password.'))
        return current_password

    def save(self):
        user = self.context['request'].user
        user.set_password(self.data['new_password'])
        user.save()
