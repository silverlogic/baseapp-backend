from django import forms


class CustomAllauthSignupForm(forms.Form):
    """
    Custom allauth signup form that adds first and last name to the user.
    """

    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)

    def signup(self, request, user):
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.save()
        return user
