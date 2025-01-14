from django import forms
from baseapp_auth.utils.referral_utils import get_user_referral_model, use_referrals
from baseapp_referrals.utils import get_user_from_referral_code


class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label="First Name")
    last_name = forms.CharField(max_length=30, label="Last Name")
    referral_code = forms.CharField(max_length=30, label="Referral Code", required=False)

    def signup(self, request, user):
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()
        referral_code = self.cleaned_data["referral_code"]
        if use_referrals() and referral_code:
            referrer = get_user_from_referral_code(referral_code)
            if referrer:
                get_user_referral_model().objects.create(referrer=referrer, referee=user)
        return user
