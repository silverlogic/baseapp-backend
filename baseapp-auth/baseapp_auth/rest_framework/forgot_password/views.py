from baseapp_auth.emails import send_password_reset_email
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import mixins, response, status, viewsets
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

from .serializers import ForgotPasswordSerializer, ResetPasswordSerializer


class ForgotPasswordBaseViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    serializer_class = ForgotPasswordSerializer

    def get_urlsafe_user_token(self, user):
        pass

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        associated_user = User.objects.get(email=serializer.data["email"])
        token = self.get_urlsafe_user_token(associated_user)
        info = {"email": associated_user.email, "token": token}
        send_password_reset_email(info)
        return response.Response(ForgotPasswordSerializer(info).data, status=status.HTTP_200_OK)


class ForgotPasswordViewSet(ForgotPasswordBaseViewSet):
    def get_urlsafe_user_token(self, user):
        user_id = user.pk
        user_token = default_token_generator.make_token(user)
        return urlsafe_base64_encode(force_bytes(signing.dumps([user_id, user_token])))


class ForgotPasswordJwtViewSet(ForgotPasswordBaseViewSet):
    def get_urlsafe_user_token(self, user):
        refresh = RefreshToken.for_user(user)
        return refresh.access_token


class ResetPasswordViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    serializer_class = ResetPasswordSerializer

    def create(self, request, *arg, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({})
