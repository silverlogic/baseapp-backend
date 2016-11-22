from django.utils.translation import ugettext as _

from rest_framework import serializers

from apps.referrals.models import UserReferral
from apps.referrals.utils import get_user_from_referral_code
from apps.users.models import User


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()
    referral_code = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, email):
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(_('That email is already in use.  Choose another.'))
        return email

    def validate_referral_code(self, referral_code):
        if referral_code:
            self.referrer = get_user_from_referral_code(referral_code)
            if not self.referrer:
                raise serializers.ValidationError(_('Invalid referral code.'))
        return referral_code

    def validate(self, data):
        data.pop('referral_code', None)
        return data

    def save(self):
        validated_data = self.validated_data
        user = User.objects.create_user(**validated_data)
        if hasattr(self, 'referrer'):
            UserReferral.objects.create(referrer=self.referrer, referee=user)
        return user
