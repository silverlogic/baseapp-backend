import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

import baseapp_auth.tests.helpers as h

User = get_user_model()
UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


class TestAllauthHeadlessSignup:
    endpoint_path = "/_allauth/app/v1/auth/signup"

    @pytest.fixture
    def signup_data(self):
        return {
            "email": "newuser@example.com",
            "password": "securepassword123",  # NOSONAR
        }

    def test_signup_creates_user_and_returns_tokens(self, client, signup_data):
        r = client.post(self.endpoint_path, signup_data)
        assert r.status_code == 200

        assert User.objects.filter(email=signup_data["email"]).exists()
        user = User.objects.get(email=signup_data["email"])
        assert user.check_password(signup_data["password"])  # NOSONAR

        response_data = r.json()
        assert "meta" in response_data
        assert "access_token" in response_data["meta"]
        assert "refresh_token" in response_data["meta"]
        assert response_data["meta"]["is_authenticated"] is True

    def test_signup_with_duplicate_email_returns_error(self, client, signup_data):
        UserFactory(email=signup_data["email"])
        r = client.post(self.endpoint_path, signup_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data

    def test_signup_with_weak_password_returns_error(self, client, signup_data):
        signup_data["password"] = "123"  # NOSONAR
        r = client.post(self.endpoint_path, signup_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data

    def test_signup_email_is_normalized_to_lowercase(self, client, signup_data):
        signup_data["email"] = "NewUser@EXAMPLE.COM"
        r = client.post(self.endpoint_path, signup_data)
        assert r.status_code == 200

        assert User.objects.filter(email="newuser@example.com").exists()


class TestAllauthHeadlessLogin:
    endpoint_path = "/_allauth/app/v1/auth/login"

    @pytest.fixture
    def login_data(self):
        return {
            "email": "testuser@example.com",
            "password": "testpassword123",  # NOSONAR
        }

    @pytest.fixture
    def existing_user(self, login_data):
        return UserFactory(email=login_data["email"], password=login_data["password"])  # NOSONAR

    def test_login_with_valid_credentials_returns_tokens(self, client, login_data, existing_user):
        r = client.post(self.endpoint_path, login_data)
        assert r.status_code == 200

        response_data = r.json()
        assert response_data["status"] == 200
        assert "meta" in response_data
        assert "access_token" in response_data["meta"]
        assert "refresh_token" in response_data["meta"]
        assert response_data["meta"]["is_authenticated"] is True

        assert "data" in response_data
        assert "user" in response_data["data"]
        assert response_data["data"]["user"]["email"] == login_data["email"]

    def test_login_with_invalid_email_returns_error(self, client, login_data):
        login_data["email"] = "nonexistent@example.com"
        r = client.post(self.endpoint_path, login_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data

    def test_login_with_invalid_password_returns_error(self, client, login_data, existing_user):
        login_data["password"] = "wrongpassword"  # NOSONAR
        r = client.post(self.endpoint_path, login_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data


class TestAllauthHeadlessLogout:
    endpoint_path = "/_allauth/app/v1/auth/session"
    login_endpoint = "/_allauth/app/v1/auth/login"

    @pytest.fixture
    def authenticated_client_with_tokens(self):
        user = UserFactory(email="testuser@example.com", password="testpass123")  # NOSONAR
        client = APIClient()

        login_response = client.post(
            self.login_endpoint,
            {"email": user.email, "password": "testpass123"},  # NOSONAR
        )

        tokens = login_response.json()["meta"]
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        return client, access_token, refresh_token, user

    def test_logout_invalidates_access_token(self, authenticated_client_with_tokens):
        client, access_token, refresh_token, user = authenticated_client_with_tokens

        client.delete(self.endpoint_path)

        me_endpoint = "/v1/users/me"
        r = client.get(me_endpoint)
        assert r.status_code == 401


class TestAllauthHeadlessTokenRefresh:
    login_endpoint = "/_allauth/app/v1/auth/login"

    @pytest.fixture
    def refresh_token(self):
        user = UserFactory(email="testuser@example.com", password="testpass123")  # NOSONAR
        client = APIClient()

        login_response = client.post(
            self.login_endpoint,
            {"email": user.email, "password": "testpass123"},  # NOSONAR
        )

        return login_response.json()["meta"]["refresh_token"]

    @pytest.mark.skip(
        reason="Token refresh endpoint structure depends on allauth.headless configuration"
    )
    def test_refresh_with_valid_token_returns_new_tokens(self, client, refresh_token):
        pass


class TestAllauthHeadlessPasswordReset:
    reset_endpoint = "/_allauth/app/v1/auth/password/request"

    @pytest.fixture
    def existing_user(self):
        return UserFactory(email="testuser@example.com", password="oldpassword123")  # NOSONAR

    def test_password_reset_request_returns_success(self, client, existing_user):
        r = client.post(self.reset_endpoint, {"email": existing_user.email})
        assert r.status_code in [200, 302]


class TestAllauthHeadlessProtectedEndpoints:
    login_endpoint = "/_allauth/app/v1/auth/login"
    protected_endpoint = "/v1/users/me"

    @pytest.fixture
    def access_token_and_user(self):
        user = UserFactory(email="testuser@example.com", password="testpass123")  # NOSONAR
        client = APIClient()

        login_response = client.post(
            self.login_endpoint,
            {"email": user.email, "password": "testpass123"},  # NOSONAR
        )

        return login_response.json()["meta"]["access_token"], user

    def test_protected_endpoint_rejects_invalid_token(self, client):
        client.credentials(HTTP_AUTHORIZATION="Bearer invalid_token")
        r = client.get(self.protected_endpoint)
        h.responseUnauthorized(r)

    def test_protected_endpoint_rejects_missing_token(self, client):
        r = client.get(self.protected_endpoint)
        h.responseUnauthorized(r)

    def test_protected_endpoint_rejects_malformed_authorization_header(self, client):
        client.credentials(HTTP_AUTHORIZATION="InvalidFormat token123")
        r = client.get(self.protected_endpoint)
        h.responseUnauthorized(r)
