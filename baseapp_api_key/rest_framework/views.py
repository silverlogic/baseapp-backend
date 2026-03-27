from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings as drf_api_settings

from baseapp_api_key.models import APIKey


class APIKeyViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    authentication_classes = drf_api_settings.DEFAULT_AUTHENTICATION_CLASSES

    expiry_time_seconds = 60 * 60  # 1 hour by default, can be overridden in subclass

    def get_key_name(self, request):
        return "auto-generated-key"

    def create(self, request, *args, **kwargs):
        unencrypted_api_key = APIKey.objects.generate_unencrypted_api_key()
        encrypted_api_key = APIKey.objects.encrypt(unencrypted_value=unencrypted_api_key)
        expiry_date = (
            timezone.now() + timezone.timedelta(seconds=self.expiry_time_seconds)
            if self.expiry_time_seconds is not None
            else None
        )
        APIKey.objects.create(
            user=request.user,
            name=self.get_key_name(request),
            encrypted_api_key=encrypted_api_key,
            expiry_date=expiry_date,
        )

        return Response(
            {
                "api_key": unencrypted_api_key,
                "expires_in_seconds": self.expiry_time_seconds,
            }
        )
