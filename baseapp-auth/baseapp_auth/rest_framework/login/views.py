from rest_framework import response, viewsets
from rest_framework.permissions import AllowAny
from trench.views.authtoken import MFALoginViewSetMixin

from .serializers import LoginSerializer


class LoginViewSet(viewsets.GenericViewSet):
    serializer_class = LoginSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return response.Response({"token": token.key})


class LoginMfaViewSet(viewsets.GenericViewSet, MFALoginViewSetMixin):
    serializer_class = LoginSerializer
    permission_classes = (AllowAny,)
