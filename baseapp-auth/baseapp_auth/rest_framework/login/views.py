from baseapp_auth.rest_framework.mfa.mixins import MFAJWTLoginViewSetMixin
from rest_framework import response, viewsets
from rest_framework.permissions import AllowAny
from trench.views.authtoken import MFAAuthTokenViewSetMixin

from .serializers import LoginSerializer


class AuthTokenViewSet(viewsets.GenericViewSet):
    serializer_class = LoginSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return response.Response({"token": token.key})


class MfaAuthTokenViewSet(viewsets.GenericViewSet, MFAAuthTokenViewSetMixin):
    serializer_class = LoginSerializer
    permission_classes = (AllowAny,)


class MfaJwtViewSet(viewsets.GenericViewSet, MFAJWTLoginViewSetMixin):
    serializer_class = LoginSerializer
    permission_classes = (AllowAny,)
