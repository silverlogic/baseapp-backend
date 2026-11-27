from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from baseapp_profiles.conf import invitation_public_rate


class InvitationTokenThrottle(SimpleRateThrottle):
    """
    Rate-limits the public invitation endpoints per client IP
    (`BASEAPP_PROFILES_INVITATION_PUBLIC_RATE`; `None` turns it off).
    """

    scope = "baseapp_profiles_invitation_token"

    def get_rate(self) -> str | None:
        return invitation_public_rate()

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
