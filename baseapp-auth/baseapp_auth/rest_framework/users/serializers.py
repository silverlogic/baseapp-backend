from django.utils.translation import ugettext_lazy as _

from avatar.models import Avatar
from avatar.utils import invalidate_cache
from rest_framework import serializers

from apps.api.serializers import ModelSerializer
from apps.users.models import User

from .fields import AvatarField


class UserSerializer(ModelSerializer):
    avatar = AvatarField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'is_email_verified', 'new_email', 'is_new_email_verified',
                  'avatar',)
        read_only_fields = ('email', 'is_email_verified', 'new_email', 'is_new_email_confirmed')

    def update(self, instance, validated_data):
        if 'avatar' in validated_data:
            avatar = validated_data.pop('avatar')
            if avatar:
                Avatar.objects.create(user=instance, primary=True, avatar=avatar)
            else:
                instance.avatar_set.all().delete()
            invalidate_cache(instance, sizes=[1024, 64])
        return super().update(instance, validated_data)


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
