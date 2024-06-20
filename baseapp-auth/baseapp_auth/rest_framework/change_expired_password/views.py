from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, response, status, viewsets

User = get_user_model()

from .serializers import ChangeExpiredPasswordSerializer


class ChangeExpiredPasswordViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    serializer_class = ChangeExpiredPasswordSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(
            {"detail": _("success")},
            status=status.HTTP_200_OK,
        )
