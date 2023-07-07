from rest_framework import response, viewsets
from rest_framework.permissions import AllowAny
from trench.views.authtoken import MFALoginViewSetMixin
from baseapp_auth.rest_framework.login.serializers import LoginSerializer


class LoginMfaViewSet(viewsets.GenericViewSet, MFALoginViewSetMixin):
    serializer_class = LoginSerializer
    permission_classes = (AllowAny,)
