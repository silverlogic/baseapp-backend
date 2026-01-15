import warnings

from rest_framework import status, viewsets
from rest_framework.response import Response

from baseapp_auth.emails import send_welcome_email

from ..users.serializers import UserSerializer
from .serializers import RegisterSerializer


class RegisterViewSet(viewsets.GenericViewSet):
    """
    DEPRECATED: Use /v1/_allauth/app/v1/auth/signup instead.
    """

    serializer_class = RegisterSerializer
    permission_classes = ()

    def create(self, request, *args, **kwargs):
        warnings.warn(
            "The /v1/register endpoint is deprecated. "
            "Use /v1/_allauth/app/v1/auth/signup instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.perform_create(serializer)
        return Response(
            UserSerializer(user, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        user = serializer.save()
        send_welcome_email(user)
        return user
