from unittest.mock import MagicMock, patch

import pytest
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken

from baseapp_core.authentication import (
    authenticate_jwt,
    get_user_from_access_token,
    refresh_access_token,
)
from baseapp_core.tests.factories import UserFactory

JWT_AUTH = "rest_framework_simplejwt.authentication.JWTAuthentication"


class TestGetUserFromAccessToken:
    def test_returns_none_for_empty_token(self):
        assert get_user_from_access_token(None) is None
        assert get_user_from_access_token("") is None

    @patch(f"{JWT_AUTH}.get_user")
    @patch(f"{JWT_AUTH}.get_validated_token")
    def test_returns_user_for_valid_token(self, mock_validate, mock_get_user):
        user = MagicMock()
        mock_validate.return_value = "validated"
        mock_get_user.return_value = user

        assert get_user_from_access_token("good-token") is user
        mock_validate.assert_called_once_with("good-token")
        mock_get_user.assert_called_once_with("validated")

    @patch(f"{JWT_AUTH}.get_validated_token", side_effect=InvalidToken("expired"))
    def test_invalid_token_returns_none_and_logs_debug(self, mock_validate):
        with patch("baseapp_core.authentication.logger") as mock_logger:
            result = get_user_from_access_token("expired-token")

        assert result is None
        mock_logger.debug.assert_called_once()
        mock_logger.exception.assert_not_called()


class TestRefreshAccessToken:
    def test_returns_none_for_empty_token(self):
        assert refresh_access_token(None) is None

    def test_invalid_refresh_returns_none_and_logs_debug(self):
        with patch("baseapp_core.authentication.logger") as mock_logger:
            result = refresh_access_token("not-a-real-token")

        assert result is None
        mock_logger.debug.assert_called_once()
        mock_logger.exception.assert_not_called()

    @patch("rest_framework_simplejwt.tokens.RefreshToken")
    def test_returns_new_access_token_for_valid_refresh(self, mock_refresh_cls):
        mock_refresh_cls.return_value.access_token = "new-access"
        assert refresh_access_token("valid-refresh") == "new-access"


class TestAuthenticateJwt:
    @patch("baseapp_core.authentication.get_user_from_access_token")
    def test_returns_user_when_access_token_valid(self, mock_get_user):
        user = MagicMock()
        mock_get_user.return_value = user

        result_user, new_token = authenticate_jwt("access", "refresh")

        assert result_user is user
        assert new_token is None
        mock_get_user.assert_called_once_with("access")

    @patch("baseapp_core.authentication.refresh_access_token", return_value="new-access")
    @patch("baseapp_core.authentication.get_user_from_access_token")
    def test_refreshes_when_access_token_expired(self, mock_get_user, mock_refresh):
        user = MagicMock()
        mock_get_user.side_effect = [None, user]  # original fails, refreshed succeeds

        result_user, new_token = authenticate_jwt("expired", "refresh")

        assert result_user is user
        assert new_token == "new-access"
        mock_refresh.assert_called_once_with("refresh")

    @patch("baseapp_core.authentication.refresh_access_token", return_value=None)
    @patch("baseapp_core.authentication.get_user_from_access_token", return_value=None)
    def test_returns_none_when_refresh_fails(self, mock_get_user, mock_refresh):
        assert authenticate_jwt("expired", "bad-refresh") == (None, None)

    @patch("baseapp_core.authentication.refresh_access_token")
    @patch("baseapp_core.authentication.get_user_from_access_token", return_value=None)
    def test_does_not_refresh_without_refresh_token(self, mock_get_user, mock_refresh):
        assert authenticate_jwt("expired", None) == (None, None)
        mock_refresh.assert_not_called()


@pytest.mark.django_db
class TestAuthenticateJwtIntegration:
    """End-to-end checks against real simplejwt tokens (the JWT layer is not mocked)."""

    def test_valid_access_token_resolves_real_user(self):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)

        authed_user, new_token = authenticate_jwt(str(refresh.access_token), None)

        assert authed_user == user
        assert new_token is None

    def test_invalid_access_with_valid_refresh_mints_new_token(self):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)

        authed_user, new_token = authenticate_jwt("not-a-valid-token", str(refresh))

        assert authed_user == user
        assert new_token  # a fresh access token was issued for the same user
