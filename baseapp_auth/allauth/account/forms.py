from django import forms


class CustomAllauthSignupForm(forms.Form):
    """
    Django allauth signup hook for collecting extra user fields.
    """

    # allauth expects a plain Django Form implementing `signup(request, user)`
    # See: https://docs.allauth.org/en/latest/account/configuration.html

    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)

    def signup(self, request, user):
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.save()
        return user
