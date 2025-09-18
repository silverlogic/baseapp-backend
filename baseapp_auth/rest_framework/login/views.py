from rest_framework import response, viewsets
from rest_framework.permissions import AllowAny
from trench.views.authtoken import MFAAuthTokenViewSetMixin

from baseapp_auth.rest_framework.mfa.mixins import MFAJWTLoginViewSetMixin

from .helpers import redirect_if_user_has_expired_password
from .serializers import LoginSerializer


class BaseAuthViewSet(viewsets.GenericViewSet):
    serializer_class = LoginSerializer


class AuthTokenViewSet(BaseAuthViewSet):

    @redirect_if_user_has_expired_password
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return response.Response({"token": token.key})


class MfaAuthTokenViewSet(BaseAuthViewSet, MFAAuthTokenViewSetMixin):
    permission_classes = (AllowAny,)

    @redirect_if_user_has_expired_password
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.first_step_response(serializer.user)


class MfaJwtViewSet(BaseAuthViewSet, MFAJWTLoginViewSetMixin):
    permission_classes = (AllowAny,)

    @redirect_if_user_has_expired_password
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.first_step_response(serializer.user)
