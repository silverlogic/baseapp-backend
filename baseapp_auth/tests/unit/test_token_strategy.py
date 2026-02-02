from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest
from django.test import override_settings

from baseapp_auth.tokens import AllAuthUserProfileJWTTokenStrategy

pytestmark = pytest.mark.django_db


class TestAllAuthUserProfileJWTTokenStrategy:
    def test_returns_none_when_parent_returns_none(self):
        strategy = AllAuthUserProfileJWTTokenStrategy()
        request = HttpRequest()

        with patch(
            "baseapp_auth.tokens.AllAuthJWTTokenStrategy.create_access_token_payload",
            return_value=None,
        ):
            assert strategy.create_access_token_payload(request) is None

    def test_returns_payload_when_user_not_authenticated(self):
        strategy = AllAuthUserProfileJWTTokenStrategy()
        request = HttpRequest()
        request.user = MagicMock(is_authenticated=False)

        with patch(
            "baseapp_auth.tokens.AllAuthJWTTokenStrategy.create_access_token_payload",
            return_value={"foo": "bar"},
        ):
            result = strategy.create_access_token_payload(request)

        assert result == {"foo": "bar"}

    @override_settings(JWT_CLAIM_SERIALIZER_CLASS=None)
    def test_returns_payload_when_no_claim_serializer_configured(self):
        strategy = AllAuthUserProfileJWTTokenStrategy()
        request = HttpRequest()
        request.user = MagicMock(is_authenticated=True)

        with patch(
            "baseapp_auth.tokens.AllAuthJWTTokenStrategy.create_access_token_payload",
            return_value={"foo": "bar"},
        ):
            result = strategy.create_access_token_payload(request)

        assert result == {"foo": "bar"}

    @override_settings(
        JWT_CLAIM_SERIALIZER_CLASS="baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"
    )
    def test_merges_user_data_into_payload(self):
        strategy = AllAuthUserProfileJWTTokenStrategy()
        request = HttpRequest()

        user = MagicMock(is_authenticated=True)
        request.user = user

        base_payload = {"foo": "bar"}
        user_data = {"id": 1, "email": "test@example.com"}

        with patch(
            "baseapp_auth.tokens.AllAuthJWTTokenStrategy.create_access_token_payload",
            return_value=base_payload.copy(),
        ), patch("baseapp_auth.tokens.import_string") as mock_import:
            serializer_cls = MagicMock()
            serializer_instance = MagicMock()
            serializer_instance.data = user_data
            serializer_cls.return_value = serializer_instance
            mock_import.return_value = serializer_cls

            result = strategy.create_access_token_payload(request)

        assert result == {**base_payload, **user_data}
        serializer_cls.assert_called_once_with(user)

    @override_settings(JWT_CLAIM_SERIALIZER_CLASS="invalid.path.Serializer")
    def test_serializer_errors_are_swallowed(self):
        strategy = AllAuthUserProfileJWTTokenStrategy()
        request = HttpRequest()
        request.user = MagicMock(is_authenticated=True)

        with patch(
            "baseapp_auth.tokens.AllAuthJWTTokenStrategy.create_access_token_payload",
            return_value={"foo": "bar"},
        ), patch(
            "baseapp_auth.tokens.import_string",
            side_effect=Exception("boom"),
        ):
            result = strategy.create_access_token_payload(request)

        assert result == {"foo": "bar"}
