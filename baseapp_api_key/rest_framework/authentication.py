import typing

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from baseapp_api_key.models import APIKey, BaseAPIKey


class BaseAPIKeyAuthentication(BaseAuthentication):
    """
    HTTP Basic authentication against APIKey.
    """

    APIKeyModel: typing.Type[BaseAPIKey]

    def authenticate(self, request):
        """
        Authenticate the request and return a two-tuple of (user, token).
        """

        unencrypted_api_key = request.META.get(settings.BA_API_KEY_REQUEST_HEADER, None)

        if isinstance(unencrypted_api_key, str):
            encrypted_api_key = self.APIKeyModel.objects.encrypt(
                unencrypted_value=unencrypted_api_key
            )
            api_key = (
                self.APIKeyModel.objects.all().filter(encrypted_api_key=encrypted_api_key).first()
            )

            if api_key is None:
                raise exceptions.AuthenticationFailed(_("Invalid APIKey."))

            if api_key.is_expired:
                raise exceptions.AuthenticationFailed(_("APIKey is expired."))

            if not api_key.user.is_active:
                raise exceptions.AuthenticationFailed(_("User inactive or deleted."))

            return (api_key.user, None)

        return None

    def authenticate_header(self, request):
        return settings.BA_API_KEY_REQUEST_HEADER


class APIKeyAuthentication(BaseAPIKeyAuthentication):
    APIKeyModel = APIKey
