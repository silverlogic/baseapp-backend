from django.utils.functional import SimpleLazyObject

from rest_framework_simplejwt.authentication import JWTAuthentication
from baseapp_core.graphql.middlewares import JWTAuthentication as GraphQLJWTAuthentication
from .utils import get_user_agent, get_user_ip_geolocation
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from baseapp_devices.models import UserDevice

class UserAgentMiddleware(object):

    def __init__(self, get_response=None):
        if get_response is not None:
            self.get_response = get_response

    def __call__(self, request):
        self.process_request(request)
        return self.get_response(request)

    def process_request(self, request):
        request.user_agent = SimpleLazyObject(lambda: get_user_agent(request))
        request.ip_geolocation = SimpleLazyObject(lambda: get_user_ip_geolocation(request))


class DeviceIDJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        user_auth_tuple = super().authenticate(request)
        if user_auth_tuple is not None:
            user, token = user_auth_tuple
            if not UserDevice.objects.filter(user=user, device_id=token.get("device_id")).exists():
                raise InvalidToken({"detail": "Invalid token"})
        return user_auth_tuple


class DeviceIDGraphQLJWTAuthentication(DeviceIDJWTAuthentication, GraphQLJWTAuthentication):
    pass
