from typing import Any, Callable, Dict, Optional

from allauth.headless.tokens.sessions import SessionTokenStrategy
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken


class AuthTokenSessionTokenStrategy(SessionTokenStrategy):
    """
    A SessionTokenStrategy that uses rest_framwork authtoken
    """

    _claim_serializer_class = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)

    def create_access_token_payload(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        if (user := request.user) and request.user.is_authenticated:
            token, _ = Token.objects.get_or_create(user=user)
            return dict(access_token=token.key)
        return super(AuthTokenSessionTokenStrategy, self).create_access_token_payload(
            request=request
        )


class JWTSessionTokenStrategy(SessionTokenStrategy):
    """
    A SessionTokenStrategy that uses jtw
    """

    _claim_serializer_class = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)

    def create_access_token_payload(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        if (user := request.user) and request.user.is_authenticated:
            try:
                claim_serializer_class: Callable = import_string(
                    self.__class__._claim_serializer_class
                )
                token = RefreshToken.for_user(user=user)
                data = claim_serializer_class(user).data
                for key, value in data.items():
                    token[key] = value

                if "baseapp_devices" in settings.INSTALLED_APPS:
                    from baseapp_devices.models import UserDevice
                    from baseapp_devices.utils import get_device_id

                    device_id = get_device_id(request.user_agent, request.ip_geolocation)
                    token["device_id"] = device_id
                    user_agent = request.user_agent
                    UserDevice.objects.update_or_create(
                        user=user,
                        device_id=device_id,
                        defaults={
                            "device_info": {
                                "device_family": user_agent.device.family,
                                "os_family": user_agent.os.family,
                                "os_version": user_agent.os.version,
                                "browser_family": user_agent.browser.family,
                                "browser_version": user_agent.browser.version,
                                "is_mobile": user_agent.is_mobile,
                                "is_tablet": user_agent.is_tablet,
                                "is_pc": user_agent.is_pc,
                            },
                            "location": dict(request.ip_geolocation),
                            "ip_address": request.ip_geolocation.get("query"),
                            "last_login": timezone.now(),
                        },
                    )
                return dict(access_token=dict(refresh=str(token), access=str(token.access_token)))
            except ImportError as error:
                msg = "Could not import serializer '%s'" % self.__class__._claim_serializer_class
                raise ImportError(msg) from error
        return super(JWTSessionTokenStrategy, self).create_access_token(request=request)
