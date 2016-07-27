from django.utils.translation import ugettext_lazy as _

from avatar.models import Avatar
from rest_framework import serializers

from apps.api.serializers import ModelSerializer
from apps.referrals.utils import get_referral_code
from apps.users.models import User

from .fields import AvatarField


class UserBaseSerializer(ModelSerializer):
    avatar = AvatarField(required=False, allow_null=True)
    referral_code = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'is_email_verified', 'new_email', 'is_new_email_verified',
                  'referral_code', 'avatar', 'first_name', 'last_name',)
        private_fields = ('email', 'is_email_verified', 'new_email', 'is_new_email_verified',
                          'referral_code',)
        read_only_fields = ('email', 'is_email_verified', 'new_email', 'is_new_email_confirmed',)

    def get_referral_code(self, user):
        return get_referral_code(user)


class UserSerializer(UserBaseSerializer):
    class Meta(UserBaseSerializer.Meta):
        pass

    def update(self, instance, validated_data):
        if 'avatar' in validated_data:
            avatar = validated_data.pop('avatar')
            if avatar:
                Avatar.objects.create(user=instance, primary=True, avatar=avatar)
            else:
                instance.avatar_set.all().delete()
        return super().update(instance, validated_data)

    def to_representation(self, user):
        request = self.context['request']
        if request.user.is_authenticated() and request.user.pk == user.pk:
            return super().to_representation(user)
        else:
            return UserPublicSerializer(user).data


class UserPublicSerializer(UserBaseSerializer):
    class Meta(UserSerializer.Meta):
        fields = tuple(set(UserSerializer.Meta.fields) - set(UserSerializer.Meta.private_fields))
        read_only_fields = tuple(set(UserSerializer.Meta.read_only_fields) - set(UserSerializer.Meta.private_fields))


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
