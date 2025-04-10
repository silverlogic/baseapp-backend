from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from django.conf import settings
from rest_framework import response, status, viewsets

from baseapp_auth.exceptions import UserPasswordExpiredException
from baseapp_auth.rest_framework.login.serializers import (
    LoginChangeExpiredPasswordRedirectSerializer,
)
from baseapp_auth.tokens import ChangeExpiredPasswordTokenGenerator

P = ParamSpec("P")
T = TypeVar("T")


def redirect_if_user_has_expired_password(f: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator that redirects to the change expired password frontend url if the user's password is expired.
    """

    @wraps(f)
    def _inner(self: viewsets.GenericViewSet, *args: P.args, **kwargs: P.kwargs) -> T:
        assert issubclass(self.__class__, viewsets.GenericViewSet)
        try:
            return f(self, *args, **kwargs)
        except UserPasswordExpiredException as e:
            self.request.user = e.user
            token = ChangeExpiredPasswordTokenGenerator().make_token(self.request.user)
            url = settings.FRONT_CHANGE_EXPIRED_PASSWORD_URL.format(token=token)
            serializer = LoginChangeExpiredPasswordRedirectSerializer(
                data=dict(redirect_url=url), context=self.get_serializer_context()
            )
            serializer.is_valid(raise_exception=True)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

    return _inner
