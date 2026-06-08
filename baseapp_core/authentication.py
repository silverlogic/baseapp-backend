from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from channels.db import database_sync_to_async

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


def get_user_from_access_token(access_token: str | None) -> AbstractBaseUser | None:
    """Return the user for a valid JWT access token, or ``None``.

    An invalid or expired token is an expected outcome — tokens are short-lived and
    clients reconnect — so it resolves to ``None`` and is logged at debug level rather
    than raised or logged as an exception.
    """
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import (
        AuthenticationFailed,
        InvalidToken,
        TokenError,
    )

    if not access_token:
        return None

    auth = JWTAuthentication()
    try:
        validated_token = auth.get_validated_token(access_token)
        return auth.get_user(validated_token)
    except (AuthenticationFailed, InvalidToken, TokenError) as e:
        logger.debug("JWT access token rejected: %s", e)
        return None


def refresh_access_token(refresh_token: str | None) -> str | None:
    """Mint a new access token from a refresh token, or ``None`` if it is invalid."""
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import RefreshToken

    if not refresh_token:
        return None

    try:
        return str(RefreshToken(refresh_token).access_token)
    except TokenError as e:
        logger.debug("JWT refresh token rejected: %s", e)
        return None


def authenticate_jwt(
    access_token: str | None, refresh_token: str | None = None
) -> tuple[AbstractBaseUser | None, str | None]:
    """Resolve a user from an access token, refreshing it when expired.

    Returns ``(user, new_access_token)``. ``new_access_token`` is set only when a
    refresh actually occurred (so the caller can propagate it). Authentication failure
    is expected and never raises — both values are ``None``.
    """
    user = get_user_from_access_token(access_token)

    new_access_token = None
    if user is None and refresh_token:
        new_access_token = refresh_access_token(refresh_token)
        if new_access_token:
            user = get_user_from_access_token(new_access_token)

    return user, new_access_token


authenticate_jwt_async = database_sync_to_async(authenticate_jwt)
