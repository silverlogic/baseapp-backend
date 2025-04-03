from rest_framework import response, viewsets
from rest_framework.decorators import action

from baseapp_auth.rest_framework.users.permissions import IsAnonymous

from .serializers import AuthTokenPreAuthSerializer, JWTPreAuthSerializer


class PreAuthViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAnonymous]

    @action(
        detail=False,
        methods=["POST"],
        serializer_class=AuthTokenPreAuthSerializer,
        url_path="auth-token",
    )
    def auth_token(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return response.Response(dict(token=instance.key))

    @action(
        detail=False,
        methods=["POST"],
        serializer_class=JWTPreAuthSerializer,
    )
    def jwt(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return response.Response(dict(refresh=str(instance), access=str(instance.access_token)))
