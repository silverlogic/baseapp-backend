from django.conf import settings
from django.db import models

import swapper


class BaseUserDevice(models.Model):
    class Meta:
        abstract = True

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="devices",
        on_delete=models.CASCADE,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    location = models.JSONField(null=True, blank=True)
    device_info = models.JSONField(null=True, blank=True)
    device_token = models.CharField(max_length=255)
    device_id = models.CharField(max_length=255)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class UserDevice(BaseUserDevice):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_devices", "UserDevice")

    def __str__(self):
        return f"{self.user.email} - {self.ip_address}"
