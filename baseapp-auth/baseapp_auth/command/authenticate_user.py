from django.contrib.auth import authenticate, get_user_model
from django.utils.translation import gettext_lazy as _

from rest_framework.request import Request, exceptions

User = get_user_model()


def authenticate_user(request: Request, username: str, password: str):
    user = authenticate(
        request=request,
        username=username,
        password=password,
    )
    if user is None:
        raise exceptions.AuthenticationFailed(_("Unable to login with provided credentials."))
    return user
