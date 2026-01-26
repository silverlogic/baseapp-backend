import pytest
from django.contrib.auth import get_user_model

import baseapp_auth.tests.helpers as h
from baseapp_auth.tests.mixins import ApiMixin

User = get_user_model()
UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


class TestAllauthHeadlessSignup(ApiMixin):
    view_name = "headless:app:account:signup"

    @pytest.fixture
    def signup_data(self):
        return {
            "email": "newuser@example.com",
            "password": "Securepassword123.",  # NOSONAR
            "first_name": "Test",
            "last_name": "User",
        }

    def test_signup_creates_user_and_returns_tokens(self, client, signup_data):
        r = client.post(self.reverse(), signup_data)
        assert r.status_code == 200

        assert User.objects.filter(email=signup_data["email"]).exists()
        user = User.objects.get(email=signup_data["email"])
        assert user.check_password(signup_data["password"])  # NOSONAR

        response_data = r.json()
        meta = response_data.get("meta")
        assert meta is not None
        assert "access_token" in meta
        assert "refresh_token" in meta
        assert meta.get("is_authenticated")

    def test_signup_with_duplicate_email_returns_error(self, client, signup_data):
        UserFactory(email=signup_data["email"])
        r = client.post(self.reverse(), signup_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data

    def test_signup_with_weak_password_returns_error(self, client, signup_data):
        signup_data["password"] = "123"  # NOSONAR
        r = client.post(self.reverse(), signup_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data

    def test_signup_email_is_normalized_to_lowercase(self, client, signup_data):
        signup_data["email"] = "NewUser@EXAMPLE.COM"
        r = client.post(self.reverse(), signup_data)
        assert r.status_code == 200

        assert User.objects.filter(email="newuser@example.com").exists()

    def test_signup_with_missing_email_returns_error(self, client, signup_data):
        del signup_data["email"]
        r = client.post(self.reverse(), signup_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data

    def test_signup_with_missing_password_returns_error(self, client, signup_data):
        del signup_data["password"]
        r = client.post(self.reverse(), signup_data)
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data


class TestAllauthHeadlessLogin(ApiMixin):
    view_name = "headless:app:account:login"

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
        r = client.post(self.reverse(), login_data)
        h.allauthResponseOk(r)

        response_data = r.json()

        meta = response_data.get("meta")
        assert meta is not None
        assert "access_token" in meta
        assert "refresh_token" in meta
        assert meta.get("is_authenticated")

        data = response_data.get("data")
        assert data is not None
        assert "user" in data
        assert data["user"]["email"] == login_data["email"]

    def test_login_with_invalid_email_returns_error(self, client, login_data):
        login_data["email"] = "nonexistent@example.com"
        r = client.post(self.reverse(), login_data)
        h.allauthResponseBadRequest(r)

        response_data = r.json()
        assert "errors" in response_data

    def test_login_with_invalid_password_returns_error(self, client, login_data, existing_user):
        login_data["password"] = "wrongpassword"  # NOSONAR
        r = client.post(self.reverse(), login_data)
        h.allauthResponseBadRequest(r)

        response_data = r.json()
        assert "errors" in response_data

    def test_login_with_missing_email_returns_error(self, client, login_data):
        del login_data["email"]
        r = client.post(self.reverse(), login_data)
        h.allauthResponseBadRequest(r)

        response_data = r.json()
        assert "errors" in response_data

    def test_login_with_missing_password_returns_error(self, client, login_data):
        del login_data["password"]
        r = client.post(self.reverse(), login_data)
        h.allauthResponseBadRequest(r)

        response_data = r.json()
        assert "errors" in response_data


class TestAllauthHeadlessLogout(ApiMixin):
    view_name = "headless:app:account:current_session"
    protected_endpoint = "/v1/users/me"

    @pytest.fixture
    def authenticated_client_with_tokens(self, client):
        user = UserFactory(email="testuser@example.com", password="testpass123")  # NOSONAR

        login_response = client.post(
            self.reverse(view_name="headless:app:account:login"),
            {"email": user.email, "password": "testpass123"},  # NOSONAR
        )

        response_data = login_response.json()
        access_token = response_data.get("meta").get("access_token")
        refresh_token = response_data.get("meta").get("refresh_token")

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        yield client, access_token, refresh_token, user

        client.credentials()

    def test_logout_invalidates_access_token(self, authenticated_client_with_tokens):
        client, access_token, refresh_token, user = authenticated_client_with_tokens

        r = client.delete(self.reverse())
        h.allauthResponseUnauthorized(r)

        r = client.get(self.protected_endpoint)
        h.responseUnauthorized(r)

    def test_logout_without_authentication_returns_error(self, client):
        r = client.delete(self.reverse())
        h.allauthResponseUnauthorized(r)


class TestAllauthHeadlessTokenRefresh(ApiMixin):
    view_name = "headless:app:tokens:refresh"

    @pytest.fixture
    def refresh_token(self, client):
        user = UserFactory(email="testuser@example.com", password="testpass123")  # NOSONAR

        login_response = client.post(
            self.reverse(view_name="headless:app:account:login"),
            {"email": user.email, "password": "testpass123"},  # NOSONAR
        )

        response_data = login_response.json()
        refresh_token = response_data.get("meta").get("refresh_token")

        yield refresh_token

    def test_refresh_with_valid_token_returns_new_tokens(self, client, refresh_token):
        r = client.post(self.reverse(), {"refresh_token": refresh_token})
        h.allauthResponseOk(r)

        response_data = r.json()
        data = response_data.get("data")
        assert data is not None
        assert "access_token" in data

        # The refresh token rotation is configurable
        # so we may not always have a new refresh token in the response.
        if "refresh_token" in data:
            assert data["refresh_token"] != refresh_token

    def test_refresh_with_invalid_token_returns_error(self, client):
        r = client.post(self.reverse(), {"refresh_token": "invalid_token"})
        h.allauthResponseBadRequest(r)

        response_data = r.json()
        assert response_data.get("status") == 400

    def test_refresh_with_missing_token_returns_error(self, client):
        r = client.post(self.reverse(), {})
        h.allauthResponseBadRequest(r)

        response_data = r.json()
        assert response_data.get("status") == 400


class TestAllauthHeadlessPasswordReset(ApiMixin):
    view_name = "headless:app:account:request_password_reset"

    @pytest.fixture
    def existing_user(self):
        return UserFactory(email="testuser@example.com", password="oldpassword123")  # NOSONAR

    def test_password_reset_request_returns_success(self, client, existing_user):
        r = client.post(self.reverse(), {"email": existing_user.email})
        assert r.status_code in [200, 302]

    def test_password_reset_request_with_nonexistent_email_returns_success(self, client):
        r = client.post(self.reverse(), {"email": "nonexistent@example.com"})
        assert r.status_code in [200, 302]

    def test_password_reset_request_with_missing_email_returns_error(self, client):
        r = client.post(self.reverse(), {})
        assert r.status_code == 400

        response_data = r.json()
        assert "errors" in response_data


class TestAllauthHeadlessProtectedEndpoints(ApiMixin):
    view_name = "headless:app:account:current_session"
    protected_endpoint = "/v1/users/me"

    @pytest.fixture
    def authenticated_client(self, client):
        user = UserFactory(email="testuser@example.com", password="testpass123")  # NOSONAR

        login_response = client.post(
            self.reverse(view_name="headless:app:account:login"),
            {"email": user.email, "password": "testpass123"},  # NOSONAR
        )

        response_data = login_response.json()
        access_token = response_data.get("meta").get("access_token")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        yield client, user

        client.credentials()

    def test_protected_endpoint_with_valid_token_returns_user_data(self, authenticated_client):
        client, user = authenticated_client
        r = client.get(self.protected_endpoint)
        h.responseOk(r)

        response_data = r.json()
        assert "email" in response_data
        assert response_data["email"] == user.email

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

    def test_protected_endpoint_rejects_expired_token(self, client):
        client.credentials(
            HTTP_AUTHORIZATION="Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNjAwMDAwMDAwLCJqdGkiOiJ0ZXN0In0.invalid"
        )
        r = client.get(self.protected_endpoint)
        h.responseUnauthorized(r)
