from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest

import baseapp_auth.tests.helpers as h
from baseapp_auth.graphql.middlewares import AllauthJWTTokenAuthentication

UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


def test_graphql_middleware_authenticates_user_on_first_call(django_user_client):
    middleware = AllauthJWTTokenAuthentication()
    mock_next = MagicMock(return_value="result")

    request = HttpRequest()
    request.user = MagicMock(is_authenticated=False)

    mock_info = MagicMock()
    mock_info.context = request

    user = django_user_client.user

    with patch.object(
        middleware,
        "authenticate",
        return_value=(user, None),
    ) as mock_authenticate:
        assert not hasattr(request, "_allauth_jwt_checked")

        result = middleware.resolve(mock_next, None, mock_info)

    assert result == "result"
    assert request.user == user
    assert request._allauth_jwt_checked is True
    mock_authenticate.assert_called_once_with(request)


def test_graphql_middleware_skips_authentication_when_already_checked(django_user_client):
    middleware = AllauthJWTTokenAuthentication()
    mock_next = MagicMock(return_value="result")

    request = HttpRequest()
    request.user = django_user_client.user
    request._allauth_jwt_checked = True

    mock_info = MagicMock()
    mock_info.context = request

    with patch.object(middleware, "authenticate") as mock_authenticate:
        result = middleware.resolve(mock_next, None, mock_info)

    assert result == "result"
    mock_authenticate.assert_not_called()


def test_graphql_middleware_marks_checked_even_when_authentication_fails():
    middleware = AllauthJWTTokenAuthentication()
    mock_next = MagicMock(return_value="result")

    request = HttpRequest()
    request.user = MagicMock(is_authenticated=False)

    mock_info = MagicMock()
    mock_info.context = request

    with patch.object(
        middleware,
        "authenticate",
        return_value=None,
    ) as mock_authenticate:
        result = middleware.resolve(mock_next, None, mock_info)

    assert result == "result"
    assert request._allauth_jwt_checked is True
    mock_authenticate.assert_called_once_with(request)
