from baseapp_auth.password_validators import apply_password_validators
from baseapp_auth.utils.referral_utils import get_user_referral_model, use_referrals
from baseapp_referrals.utils import get_user_from_referral_code
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField()
    referral_code = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, email):
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(_("That email is already in use.  Choose another."))
        return email

    def validate_referral_code(self, referral_code):
        if use_referrals() and referral_code:
            self.referrer = get_user_from_referral_code(referral_code)
            if not self.referrer:
                raise serializers.ValidationError(_("Invalid referral code."))
        return referral_code

    def validate(self, data):
        data.pop("referral_code", None)
        password = data.get("password")
        apply_password_validators(password)
        return data

    def save(self):
        validated_data = self.validated_data
        user = User.objects.create_user(**validated_data)
        if use_referrals() and hasattr(self, "referrer"):
            get_user_referral_model().objects.create(referrer=self.referrer, referee=user)
        return user
