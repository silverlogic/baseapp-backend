import baseapp_auth.tests.helpers as h
import pytest
from baseapp_auth.tests.mixins import ApiMixin
from constance.test import override_config
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from trench.backends.provider import get_mfa_handler
from trench.utils import UserTokenGenerator

pytestmark = pytest.mark.django_db

UserFactory = h.get_user_factory()


class TestLoginBase(ApiMixin):
    login_endpoint_path = ""

    def get_mfa_code(self, user):
        handler = get_mfa_handler(mfa_method=user.mfa_methods.get())
        return handler.create_code()

    def get_mfa_ephemeral_token(self, user):
        return UserTokenGenerator().make_token(user)

    def send_login_request(self, client, data):
        return client.post(self.login_endpoint_path, data)

    def assert_simple_token_response(self, r):
        assert r.data.get("token") is not None

    def assert_jwt_token_response(self, r):
        assert set(r.data.keys()) == {"access", "refresh"}

    def check_receives_auth_simple_token(self, client, data):
        UserFactory(email=data["email"], password=data["password"])
        r = self.send_login_request(client, data)
        h.responseOk(r)
        self.assert_simple_token_response(r)

    def check_receives_auth_jwt_token(self, client, data):
        UserFactory(email=data["email"], password=data["password"])
        r = self.send_login_request(client, data)
        h.responseOk(r)
        self.assert_jwt_token_response(r)

    def check_when_email_doesnt_exist(self, client, data):
        r = self.send_login_request(client, data)
        h.responseUnauthorized(r)

    def check_when_password_doesnt_match(self, client, data):
        UserFactory(email=data["email"], password="not password")
        r = self.send_login_request(client, data)
        h.responseUnauthorized(r)

    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    def check_can_login_with_not_expired_password(self, client, data):
        UserFactory(email=data["email"], password=data["password"])
        r = self.send_login_request(client, data)
        h.responseOk(r)

    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    def check_cant_login_with_expired_password(self, client, data):
        user = UserFactory(email=data["email"], password=data["password"])
        user.password_changed_date = timezone.now() - timezone.timedelta(days=1)
        user.save()
        r = self.send_login_request(client, data)
        h.responseUnauthorized(r)
        assert r.data.get("password") is not None


class TestLoginAuthToken(TestLoginBase):
    login_endpoint_path = "/v1/auth/authtoken/login"

    @pytest.fixture
    def data(self):
        return {"email": "john@doe.com", "password": "1234567890"}

    def test_can_login(self, client, data):
        self.check_receives_auth_simple_token(client, data)

    def test_when_email_doesnt_exist(self, client, data):
        self.check_when_email_doesnt_exist(client, data)

    def test_when_password_doesnt_match(self, client, data):
        self.check_when_password_doesnt_match(client, data)

    def test_can_login_with_not_expired_password(self, client, data):
        self.check_can_login_with_not_expired_password(client, data)

    def test_cant_login_with_expired_password(self, client, data):
        self.check_cant_login_with_expired_password(client, data)


class TestJwtRefresh(ApiMixin):
    login_endpoint_path = "/v1/auth/jwt/refresh"

    def test_receives_new_access_token(self, client):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        refresh_token = str(refresh)
        r = client.post(self.login_endpoint_path, {"refresh": refresh_token})
        h.responseOk(r)
        assert set(r.data.keys()) == {"access"}


class TestLoginJwt(TestLoginBase):
    login_endpoint_path = "/v1/auth/jwt/login"

    @pytest.fixture
    def data(self):
        return {"email": "john@doe.com", "password": "1234567890"}

    def test_can_login(self, client, data):
        self.check_receives_auth_jwt_token(client, data)

    def test_when_email_doesnt_exist(self, client, data):
        self.check_when_email_doesnt_exist(client, data)

    def test_when_password_doesnt_match(self, client, data):
        self.check_when_password_doesnt_match(client, data)

    def test_can_login_with_not_expired_password(self, client, data):
        self.check_can_login_with_not_expired_password(client, data)

    def test_cant_login_with_expired_password(self, client, data):
        self.check_cant_login_with_expired_password(client, data)

    def test_jwt_token_contains_user_data(self, client, data):
        user = UserFactory(email=data["email"], password=data["password"])
        r = self.send_login_request(client, data)
        authenticator = JWTAuthentication()
        validated_token = authenticator.get_validated_token(r.data["access"])

        assert validated_token["id"] == user.id
        assert validated_token["email"] == user.email
        assert validated_token["first_name"] == user.first_name
        assert validated_token["last_name"] == user.last_name


class TestLoginMfaAuthToken(TestLoginBase):
    """
    MFA with AuthToken authentication
    More detailed MFA tests can be found in the "trench" package.
    """

    login_endpoint_path = "/v1/auth/mfa/login"

    @pytest.fixture
    def data(self):
        return {"email": "john@doe.com", "password": "1234567890"}

    def test_when_email_doesnt_exist(self, client, data):
        self.check_when_email_doesnt_exist(client, data)

    def test_when_password_doesnt_match(self, client, data):
        self.check_when_password_doesnt_match(client, data)

    def test_can_login_with_not_expired_password(self, client, data):
        self.check_can_login_with_not_expired_password(client, data)

    def test_cant_login_with_expired_password(self, client, data):
        self.check_cant_login_with_expired_password(client, data)

    def test_receives_first_step_mfa_response(self, client, active_user_with_application_otp):
        user = active_user_with_application_otp
        data = {"email": user.email, "password": "1234567890"}
        r = self.send_login_request(client, data)
        h.responseOk(r)
        assert set(r.data.keys()) == {"ephemeral_token", "method"}

    def test_receives_second_step_mfa_response(self, client, active_user_with_application_otp):
        user = active_user_with_application_otp
        ephemeral_token = self.get_mfa_ephemeral_token(user)
        code = self.get_mfa_code(user)
        data = {"code": code, "ephemeral_token": ephemeral_token}
        r = client.post("/v1/auth/mfa/login/code", data)
        self.assert_simple_token_response(r)


class TestLoginMfaJwt(TestLoginBase):
    """
    MFA with JWT authentication
    """

    login_endpoint_path = "/v1/auth/mfa/jwt/login"

    @pytest.fixture
    def data(self):
        return {"email": "john@doe.com", "password": "1234567890"}

    def test_when_email_doesnt_exist(self, client, data):
        self.check_when_email_doesnt_exist(client, data)

    def test_when_password_doesnt_match(self, client, data):
        self.check_when_password_doesnt_match(client, data)

    def test_can_login_with_not_expired_password(self, client, data):
        self.check_can_login_with_not_expired_password(client, data)

    def test_cant_login_with_expired_password(self, client, data):
        self.check_cant_login_with_expired_password(client, data)

    def test_receives_first_step_mfa_response(self, client, active_user_with_application_otp):
        user = active_user_with_application_otp
        data = {"email": user.email, "password": "1234567890"}
        r = self.send_login_request(client, data)
        h.responseOk(r)
        assert set(r.data.keys()) == {"ephemeral_token", "method"}

    def test_receives_second_step_mfa_jwt_response(self, client, active_user_with_application_otp):
        user = active_user_with_application_otp
        ephemeral_token = self.get_mfa_ephemeral_token(user)
        code = self.get_mfa_code(user)
        data = {"code": code, "ephemeral_token": ephemeral_token}
        r = client.post("/v1/auth/mfa/jwt/login/code", data)
        self.assert_jwt_token_response(r)
