from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .referrals import get_user_from_referral_code


class SocialAuthBaseSerializer(serializers.Serializer):
    provider = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    referral_code = serializers.CharField(required=False, allow_blank=True)

    def validate_referral_code(self, referral_code):
        referrer = get_user_from_referral_code(referral_code)
        if not referrer:
            raise serializers.ValidationError(_("Invalid referral code."))
        return referral_code


class SocialAuthOAuth1Serializer(SocialAuthBaseSerializer):
    oauth_token = serializers.CharField()
    oauth_token_secret = serializers.CharField()
    oauth_verifier = serializers.CharField()


class SocialAuthOAuth2Serializer(SocialAuthBaseSerializer):
    code = serializers.CharField()
    redirect_uri = serializers.CharField()
