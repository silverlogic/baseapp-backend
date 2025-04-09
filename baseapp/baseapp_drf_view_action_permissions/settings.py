from django.conf import settings


class PermissionSettings:
    def __init__(self):
        self.ALLOW_ONLY_WHITELISTED_IP = getattr(settings, "ALLOW_ONLY_WHITELISTED_IP", False)
        self.IP_RESTRICT_ONLY_DJANGO_ADMIN = getattr(
            settings, "IP_RESTRICT_ONLY_DJANGO_ADMIN", False
        )
