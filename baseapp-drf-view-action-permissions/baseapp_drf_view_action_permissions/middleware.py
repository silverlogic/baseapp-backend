from .settings import PermissionSettings
from .utils import client_ip_address_is_restricted



class RestrictIpMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        permission_settings = PermissionSettings()
        response = self.get_response(request)
        if permission_settings.IP_RESTRICT_ONLY_DJANGO_ADMIN:
            if not request.path.startswith('/admin'):
                return response
        if client_ip_address_is_restricted(request):
                raise ValueError('IP address is restricted')
        
        return response