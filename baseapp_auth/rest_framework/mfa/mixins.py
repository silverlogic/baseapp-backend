from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from trench.views.base import MFAViewSetMixin

if TYPE_CHECKING:
    from rest_framework.serializers import Serializer


class MFAJWTLoginViewSetMixin(MFAViewSetMixin):
    _claim_serializer_class = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)

    def get_claim_serializer_class(self) -> type["Serializer"]:
        try:
            return import_string(self._claim_serializer_class)
        except ImportError:
            msg = "Could not import serializer '%s'" % self._claim_serializer_class
            raise ImportError(msg)

    def _successful_authentication_response(self, user) -> Response:
        token = RefreshToken.for_user(user=user)

        if self._claim_serializer_class:
            data = self.get_claim_serializer_class()(user).data
            for key, value in data.items():
                token[key] = value

        return Response(data={"refresh": str(token), "access": str(token.access_token)})
