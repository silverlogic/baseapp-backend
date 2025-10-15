import abc
import typing

from django.conf import settings
from rest_framework import permissions
from rest_framework.request import HttpRequest
from rest_framework.views import APIView

from baseapp_api_key.models import APIKey, BaseAPIKey


class BaseHasAPIKey(permissions.BasePermission):
    APIKeyModel: typing.Type[BaseAPIKey]

    @abc.abstractmethod
    def has_permission(self, request: HttpRequest, view: typing.Type[APIView]):
        unencrypted_api_key = request.META.get(settings.BA_API_KEY_REQUEST_HEADER, None)

        if isinstance(unencrypted_api_key, str):
            encrypted_api_key = self.APIKeyModel.objects.encrypt(
                unencrypted_value=unencrypted_api_key
            )
            return (
                self.APIKeyModel.objects.all()
                .filter(is_expired=False, encrypted_api_key=encrypted_api_key)
                .exists()
            )

        return False


class HasAPIKey(BaseHasAPIKey):
    APIKeyModel = APIKey
