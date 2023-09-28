from baseapp_core.rest_framework.decorators import action
from django.utils.module_loading import import_string
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

        raise Exception("Unsopported action for JWTAuthViewSet")

    @action(detail=False, methods=["POST"])
    def login(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    @action(detail=False, methods=["POST"])
    def refresh(self, request, *args, **kwargs):
        return super(TokenRefreshView, self).post(request, *args, **kwargs)
