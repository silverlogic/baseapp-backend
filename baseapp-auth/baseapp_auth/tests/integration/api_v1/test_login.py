import pytest
import tests.factories as f
import tests.helpers as h
from constance.test import override_config
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestLogin(ApiMixin):
    view_name = "login-list"

    def send_login_request(self, client, auth_method, data):
        if auth_method == "simple_token":
            return client.post(self.reverse(), data)
        elif auth_method == "jwt":
            return client.post("/v1/auth/jwt/login/", data)

    @pytest.mark.parametrize("auth_method", ["simple_token", "jwt"])
    def test_can_login(self, client, auth_method):
        data = {"email": "john@doe.com", "password": "1234567890"}
        f.UserFactory(email=data["email"], password=data["password"])
        r = self.send_login_request(client, auth_method, data)
        h.responseOk(r)

        if auth_method == "simple_token":
            assert set(r.data.keys()) == {"token"}
        elif auth_method == "jwt":
            assert set(r.data.keys()) == {"access", "refresh"}

    @pytest.mark.parametrize("auth_method", ["simple_token", "jwt"])
    def test_when_email_doesnt_exist(self, client, auth_method):
        data = {"email": "john@doe.com", "password": "1234567890"}
        r = self.send_login_request(client, auth_method, data)
        h.responseUnauthorized(r)

    @pytest.mark.parametrize("auth_method", ["simple_token", "jwt"])
    def test_when_password_doesnt_match(self, client, auth_method):
        data = {"email": "john@doe.com", "password": "1234567890"}
        f.UserFactory(email=data["email"], password="not password")
        r = self.send_login_request(client, auth_method, data)
        h.responseUnauthorized(r)

    @pytest.mark.parametrize("auth_method", ["simple_token", "jwt"])
    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    def test_can_login_with_not_expired_password(self, client, auth_method):
        data = {"email": "john@doe.com", "password": "1234567890"}
        f.UserFactory(email=data["email"], password=data["password"])
        r = self.send_login_request(client, auth_method, data)
        h.responseOk(r)

    @pytest.mark.parametrize("auth_method", ["simple_token", "jwt"])
    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    def test_cant_login_with_expired_password(self, client, auth_method):
        data = {"email": "john@doe.com", "password": "1234567890"}
        user = f.UserFactory(email=data["email"], password=data["password"])
        user.password_changed_date = timezone.now() - timezone.timedelta(days=1)
        user.save()
        r = self.send_login_request(client, auth_method, data)
        h.responseUnauthorized(r)
        assert r.data.get("password") is not None


class TestJwtAuth(ApiMixin):
    def test_can_jwt_token_contains_user_data(self, client):
        data = {"email": "john@doe.com", "password": "1234567890"}
        user = f.UserFactory(email=data["email"], password=data["password"])
        r = client.post("/v1/auth/jwt/login/", data)
        h.responseOk(r)
        authenticator = JWTAuthentication()
        validated_token = authenticator.get_validated_token(r.data["access"])

        assert validated_token["id"] == user.id
        assert validated_token["email"] == user.email
        assert validated_token["first_name"] == user.first_name
        assert validated_token["last_name"] == user.last_name


class TestMfaLogin(ApiMixin):
    """
    More detailed MFA tests can be found in the "trench" package.
    """

    view_name = "login-list"

    def send_login_request(self, client, auth_method, data):
        if auth_method == "simple_token":
            return client.post(self.reverse(), data)
        elif auth_method == "jwt":
            return client.post("/v1/auth/mfa/jwt/login/", data)

    @pytest.mark.parametrize("auth_method", ["simple_token", "jwt"])
    def test_can_login_using_mfa(self, client, active_user_with_application_otp, auth_method):
        user = active_user_with_application_otp
        data = {"email": user.email, "password": "1234567890"}
        r = self.send_login_request(client, auth_method, data)
        h.responseOk(r)
        assert set(r.data.keys()) == {"ephemeral_token", "method"}
