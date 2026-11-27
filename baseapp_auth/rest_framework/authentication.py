from allauth.headless.contrib.rest_framework.authentication import JWTTokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request


class AllAuthJWTTokenAuthentication(JWTTokenAuthentication):
    """allauth headless JWT authentication that steps aside for tokens it doesn't recognise.

    allauth's class raises ``AuthenticationFailed`` for any ``Bearer`` token that isn't one of
    its own, so DRF never tries the next authentication class. Returning ``None`` instead lets
    SimpleJWT (or any later class) authenticate the request, so clients on the SimpleJWT
    strategy keep working while allauth is the default. A token no class accepts is still
    rejected by the later classes.
    """

    def authenticate(self, request: Request) -> tuple | None:
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None
