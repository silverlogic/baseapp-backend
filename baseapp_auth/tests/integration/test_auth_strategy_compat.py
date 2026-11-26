"""Every auth strategy's token must authenticate REST requests side by side.

The allauth headless strategy is the default, but clients on the SimpleJWT or DRF authtoken
strategies must keep working: their tokens may not be rejected by the allauth authentication
class before the class that understands them gets a chance.
"""

import pytest

import baseapp_auth.tests.helpers as h

UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db

EMAIL = "strategy@example.com"
PASSWORD = "testpassword123"  # NOSONAR
ME_URL = "/v1/users/me"


@pytest.fixture
def user():
    return UserFactory(email=EMAIL, password=PASSWORD)  # NOSONAR


def test_allauth_access_token_authenticates_rest(client, user) -> None:
    r = client.post("/v1/_allauth/app/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.content
    token = r.json()["meta"]["access_token"]

    r = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

    assert r.status_code == 200, r.content
    assert r.json()["email"] == user.email


def test_simplejwt_access_token_authenticates_rest(client, user) -> None:
    r = client.post("/v1/auth/jwt/login", {"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.content
    token = r.json()["access"]

    r = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

    assert r.status_code == 200, r.content
    assert r.json()["email"] == user.email


def test_authtoken_authenticates_rest(client, user) -> None:
    r = client.post("/v1/auth/authtoken/login", {"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.content
    token = r.json()["token"]

    r = client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {token}")

    assert r.status_code == 200, r.content
    assert r.json()["email"] == user.email


def test_invalid_bearer_token_is_rejected(client, user) -> None:
    r = client.get(ME_URL, HTTP_AUTHORIZATION="Bearer not-a-token")

    assert r.status_code == 401
