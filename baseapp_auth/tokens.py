from math import floor
from typing import Any, Dict

from allauth.headless.tokens.strategies.jwt import (
    JWTTokenStrategy as AllAuthJWTTokenStrategy,
)
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.module_loading import import_string
from django.utils.timezone import timedelta

from baseapp_core.tokens import TokenGenerator


class ChangeEmailConfirmTokenGenerator(TokenGenerator):
    key_salt = "change-email"

    def get_signing_value(self, user):
        return [user.id, user.new_email, user.is_new_email_confirmed]

    @property
    def max_age(self) -> int | None:
        if (
            time_delta := getattr(
                settings, "BA_AUTH_CHANGE_EMAIL_CONFIRM_TOKEN_EXPIRATION_TIME_DELTA", None
            )
            or timedelta(days=1)  # default to 1 day
        ) and isinstance(time_delta, timedelta):
            return int(floor(time_delta.total_seconds()))
        raise ImproperlyConfigured(
            "BA_AUTH_CHANGE_EMAIL_CONFIRM_TOKEN_EXPIRATION_TIME_DELTA must be a timedelta"
        )


class ChangeEmailVerifyTokenGenerator(TokenGenerator):
    key_salt = "verify-email"

    def get_signing_value(self, user):
        return [user.id, user.new_email, user.is_new_email_confirmed]

    @property
    def max_age(self) -> int | None:
        if (
            time_delta := getattr(
                settings, "BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA", None
            )
            or timedelta(days=1)  # default to 1 day
        ) and isinstance(time_delta, timedelta):
            return int(floor(time_delta.total_seconds()))
        raise ImproperlyConfigured(
            "BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA must be a timedelta"
        )


class ConfirmEmailTokenGenerator(TokenGenerator):
    key_salt = "confirm_email"

    def get_signing_value(self, user):
        return [user.pk, user.email]

    @property
    def max_age(self) -> int | None:
        if (
            time_delta := getattr(
                settings, "BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA", None
            )
            or timedelta(days=1)  # default to 1 day
        ) and isinstance(time_delta, timedelta):
            return int(floor(time_delta.total_seconds()))
        raise ImproperlyConfigured(
            "BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA must be a timedelta"
        )


class PreAuthTokenGenerator(TokenGenerator):
    key_salt = "pre_auth_token"

    def get_signing_value(self, user):
        return [user.pk, user.email]

    @property
    def max_age(self) -> int | None:
        if hasattr(settings, "BA_AUTH_PRE_AUTH_TOKEN_EXPIRATION_TIME_DELTA"):
            _time_delta = settings.BA_AUTH_PRE_AUTH_TOKEN_EXPIRATION_TIME_DELTA
            if not isinstance(_time_delta, timedelta):
                raise ImproperlyConfigured(
                    "BA_AUTH_PRE_AUTH_TOKEN_EXPIRATION_TIME_DELTA must be a timedelta"
                )
            return int(floor(_time_delta.total_seconds()))
        return int(floor(timedelta(days=7).total_seconds()))  # default to 7 days


class ChangeExpiredPasswordTokenGenerator(TokenGenerator):
    key_salt = "change_expired_password_token"

    def get_signing_value(self, user):
        return [user.pk, user.email]

    @property
    def max_age(self) -> int | None:
        if (
            time_delta := getattr(
                settings, "BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA", None
            )
            or timedelta(minutes=5)  # default to 5 minutes
        ) and isinstance(time_delta, timedelta):
            return int(floor(time_delta.total_seconds()))
        raise ImproperlyConfigured(
            "BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA must be a timedelta"
        )


class AllAuthUserProfileJWTTokenStrategy(AllAuthJWTTokenStrategy):
    """
    AllAuth JWT token strategy that adds user profile data to the response meta field.

    Extends the default response with user data from JWT_CLAIM_SERIALIZER_CLASS,
    making profile information available in login/signup responses.
    """

    def create_access_token_payload(self, request: HttpRequest) -> Dict[str, Any] | None:
        payload = super().create_access_token_payload(request)
        if payload is None:
            return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return payload

        claim_serializer_class_path = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)
        if not claim_serializer_class_path:
            return payload

        try:
            claim_serializer_class = import_string(claim_serializer_class_path)
            user_data = claim_serializer_class(user).data
            payload.update(user_data)
        except Exception:
            pass

        return payload
