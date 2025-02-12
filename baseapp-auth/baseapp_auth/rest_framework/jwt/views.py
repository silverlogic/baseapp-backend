from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from baseapp_auth.rest_framework.jwt.serializers import LogoutDeviceSerializer
from baseapp_core.rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


class JWTAuthViewSet(TokenObtainPairView, TokenRefreshView, GenericViewSet):
    def get_serializer_class(self) -> Serializer:
        if self.action == "login":
            return import_string(api_settings.TOKEN_OBTAIN_SERIALIZER)
        elif self.action == "refresh":
            return import_string(api_settings.TOKEN_REFRESH_SERIALIZER)

        raise Exception(_("Unsupported action for JWTAuthViewSet"))

    @action(detail=False, methods=["POST"])
    def refresh(self, request, *args, **kwargs):
        return super(TokenRefreshView, self).post(request, *args, **kwargs)

    @action(detail=False, methods=["POST"], serializer_class=LogoutDeviceSerializer)
    def logoutdevice(self, request, *args, **kwargs):
        serializer = LogoutDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Device logged out successfully"},
            status=status.HTTP_200_OK,
        )
