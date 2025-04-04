from unittest.mock import MagicMock, patch

import pytest
from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.exceptions import InvalidToken

from baseapp_core.channels import JWTAuthMiddleware

pytestmark = pytest.mark.django_db


class TestBaseMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        pass


class TestJWTAuthMiddleware:
    @pytest.fixture
    def middleware(self):
        return JWTAuthMiddleware(TestBaseMiddleware(inner=None))

    @pytest.mark.asyncio
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_validated_token")
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_user")
    async def test_jwt_auth_middleware_valid_token(
        self, mock_get_user, mock_get_validated_token, middleware
    ):
        """
        Scenario:
            - A valid JWT token is provided in the Authorization header.
        Expected behavior:
            - The token is validated, and the corresponding user is set in the scope.
        """

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_get_validated_token.return_value = "valid_token"
        mock_get_user.return_value = mock_user

        scope = {"subprotocols": ["Authorization", "Bearer valid_jwt_token"]}

        async def mock_receive():
            return {}

        async def mock_send(message):
            pass

        # Act
        await middleware(scope, mock_receive, mock_send)

        # Assert
        assert scope["user"] == mock_user
        mock_get_validated_token.assert_called_once_with("Bearer valid_jwt_token")
        mock_get_user.assert_called_once_with("valid_token")

    @pytest.mark.asyncio
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_validated_token")
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_user")
    async def test_jwt_auth_middleware_invalid_token(
        self, mock_get_user, mock_get_validated_token, middleware
    ):
        """
        Scenario:
            - An invalid JWT token is provided in the Authorization header.
        Expected behavior:
            - The token validation fails, and no user is set in the scope.
        """

        mock_get_validated_token.side_effect = InvalidToken("Invalid token")

        scope = {"subprotocols": ["Authorization", "Bearer invalid_jwt_token"]}

        async def mock_receive():
            return {}

        async def mock_send(message):
            pass

        await middleware(scope, mock_receive, mock_send)

        assert "user" not in scope
        mock_get_validated_token.assert_called_once_with("Bearer invalid_jwt_token")
        mock_get_user.assert_not_called()

    @pytest.mark.asyncio
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_validated_token")
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_user")
    @patch("baseapp_core.channels.JWTAuthMiddleware.refresh_access_token")
    async def test_jwt_auth_middleware_refresh_token(
        self, mock_refresh_access_token, mock_get_user, mock_get_validated_token, middleware
    ):
        """
        Scenario:
            - An invalid JWT token is provided, but a valid refresh token is available.
        Expected behavior:
            - The access token is refreshed, and the corresponding user is set in the scope with the new token.
        """

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_get_validated_token.side_effect = [InvalidToken("Invalid token"), "new_valid_token"]
        mock_get_user.return_value = mock_user
        mock_refresh_access_token.return_value = "new_access_token"

        scope = {
            "subprotocols": [
                "Authorization",
                "Bearer invalid_jwt_token",
                "Refresh",
                "valid_refresh_token",
            ]
        }

        async def mock_receive():
            return {}

        async def mock_send(message):
            pass

        await middleware(scope, mock_receive, mock_send)

        assert scope["subprotocols"][1] == "new_access_token"
        mock_get_validated_token.assert_any_call("Bearer invalid_jwt_token")
        mock_get_validated_token.assert_any_call("new_access_token")
        mock_refresh_access_token.assert_called_once_with("valid_refresh_token")
        assert scope["user"] == mock_user
        mock_get_user.assert_called_with("new_valid_token")

    @pytest.mark.asyncio
    async def test_jwt_auth_middleware_missing_token(self, middleware):
        """
        Scenario:
            - No Authorization token is provided in the subprotocols.
        Expected behavior:
            - A ValueError is raised indicating the missing token.
        """

        scope = {"subprotocols": []}

        async def mock_receive():
            return {}

        async def mock_send(message):
            pass

        with pytest.raises(ValueError, match="Missing token"):
            await middleware(scope, mock_receive, mock_send)

    @pytest.mark.asyncio
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_validated_token")
    @patch("rest_framework_simplejwt.authentication.JWTAuthentication.get_user")
    async def test_jwt_auth_middleware_inactive_user(
        self, mock_get_user, mock_get_validated_token, middleware
    ):
        """
        Scenario:
            - A valid JWT token is provided, but the corresponding user is inactive.
        Expected behavior:
            - A ValueError is raised indicating the user is inactive or deleted.
        """

        mock_user = MagicMock()
        mock_user.is_active = False
        mock_get_validated_token.return_value = "valid_token"
        mock_get_user.return_value = mock_user

        scope = {"subprotocols": ["Authorization", "Bearer valid_jwt_token"]}

        async def mock_receive():
            return {}

        async def mock_send(message):
            pass

        with pytest.raises(ValueError, match="User inactive or deleted"):
            await middleware(scope, mock_receive, mock_send)
