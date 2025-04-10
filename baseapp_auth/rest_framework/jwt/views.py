from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from baseapp_core.rest_framework.decorators import action

from ..login.helpers import redirect_if_user_has_expired_password


class JWTAuthViewSet(TokenObtainPairView, TokenRefreshView, GenericViewSet):
    def get_serializer_class(self) -> Serializer:
        if self.action == "login":
            return import_string(api_settings.TOKEN_OBTAIN_SERIALIZER)
        elif self.action == "refresh":
            return import_string(api_settings.TOKEN_REFRESH_SERIALIZER)

        raise Exception(_("Unsupported action for JWTAuthViewSet"))

    @action(detail=False, methods=["POST"])
    @redirect_if_user_has_expired_password
    def login(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    @action(detail=False, methods=["POST"])
    def refresh(self, request, *args, **kwargs):
        return super(TokenRefreshView, self).post(request, *args, **kwargs)
