from .settings import PermissionSettings
from .utils import client_ip_address_is_restricted


class RestrictIpMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        permission_settings = PermissionSettings()
        if permission_settings.IP_RESTRICT_ONLY_DJANGO_ADMIN:
            if not request.path.startswith("/admin"):
                return self.get_response(request)

        if client_ip_address_is_restricted(request):
            raise ValueError("IP address is restricted")

        return self.get_response(request)
