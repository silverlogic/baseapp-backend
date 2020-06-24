from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import mixins, response, status, viewsets

from apps.users.emails import send_password_reset_email
from apps.users.models import User

from .serializers import ForgotPasswordSerializer, ResetPasswordSerializer


class ForgotPasswordViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    serializer_class = ForgotPasswordSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        associated_user = User.objects.get(email=serializer.data["email"])
        user_id = associated_user.pk
        user_token = default_token_generator.make_token(associated_user)
        token = urlsafe_base64_encode(force_bytes(signing.dumps([user_id, user_token])))
        info = {"email": associated_user.email, "token": token}
        send_password_reset_email(info)
        return response.Response(ForgotPasswordSerializer(info).data, status=status.HTTP_200_OK)


class ResetPasswordViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    serializer_class = ResetPasswordSerializer

    def create(self, request, *arg, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({})
