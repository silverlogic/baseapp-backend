from django.contrib.auth import get_user_model
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.response import Response

from baseapp_auth.emails import (
    send_change_email_confirm_email,
    send_change_email_verify_email,
)
from baseapp_core.rest_framework.decorators import action

from .serializers import (
    ChangeEmailConfirmSerializer,
    ChangeEmailRequestSerializer,
    ChangeEmailVerifySerializer,
)

User = get_user_model()


class ChangeEmailViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ChangeEmailRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return User.objects.all()

    def create(self, request, *args, **kwargs):
        """step 1"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_change_email_confirm_email(user)
        return Response({}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
        serializer_class=ChangeEmailConfirmSerializer,
        permission_classes=[],
    )
    def confirm(self, request, *args, **kwargs):
        """step 2"""
        try:
            user = self.get_object()
        except Http404:
            raise serializers.ValidationError({"token": [_("Invalid token.")]})
        serializer = self.get_serializer(instance=user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        send_change_email_verify_email(user)
        return Response({}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
        serializer_class=ChangeEmailVerifySerializer,
        permission_classes=[],
    )
    def verify(self, request, *args, **kwargs):
        """step 3"""
        try:
            user = self.get_object()
        except Http404:
            raise serializers.ValidationError({"token": [_("Invalid token.")]})
        serializer = self.get_serializer(instance=user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["POST"])
    def resend_confirm(self, request, *args, **kwargs):
        user = request.user
        if not user.new_email:
            raise serializers.ValidationError(
                {"non_field_errors": [_("You are not in the process of changing your email.")]}
            )
        if user.is_new_email_confirmed:
            raise serializers.ValidationError(
                {"non_field_errors": [_("Your email change has already been confirmed.")]}
            )
        send_change_email_confirm_email(user)
        return Response({}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["POST"])
    def resend_verify(self, request, *args, **kwargs):
        user = request.user
        if not user.is_new_email_confirmed:
            raise serializers.ValidationError(
                {"non_field_errors": [_("Your email change must be confirmed first.")]}
            )
        send_change_email_verify_email(user)
        return Response({}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["POST"])
    def cancel(self, request, *args, **kwrgs):
        user = request.user
        user.new_email = ""
        user.is_new_email_confirmed = False
        user.save()
        return Response({}, status=status.HTTP_200_OK)
