from django.contrib.auth import get_user_model
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.response import Response

from baseapp_auth.emails import send_welcome_email
from baseapp_core.rest_framework.decorators import action

from .serializers import ConfirmEmailSerializer

User = get_user_model()


class ConfirmEmailViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = ConfirmEmailSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return User.objects.all()

    def update(self, request, *args, **kwargs):
        try:
            user = self.get_object()
        except Http404:
            raise serializers.ValidationError({"token": [_("Invalid token.")]})
        serializer = self.get_serializer(instance=user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["POST"], permission_classes=[permissions.IsAuthenticated])
    def resend_confirm(self, request, *args, **kwargs):
        user = request.user
        if user.is_email_verified:
            raise serializers.ValidationError(
                {"non_field_errors": [_("Your email change has already been confirmed.")]}
            )
        send_welcome_email(user)
        return Response({}, status=status.HTTP_200_OK)
