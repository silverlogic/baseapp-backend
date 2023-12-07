import baseapp_auth.tests.helpers as h
import pytest
from baseapp_auth.tests.mixins import ApiMixin
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.utils.timezone import timedelta
from freezegun import freeze_time

User = get_user_model()
UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db

from baseapp_auth.tokens import PreAuthTokenGenerator


class TestPreAuthMixin(ApiMixin):
    def assert_token_response(self, r):
        raise NotImplementedError()


class TestPreAuthJWT(TestPreAuthMixin):
    view_name = "pre_auth-jwt"

    def assert_token_response(self, r):
        assert set(r.data.keys()) == {"access", "refresh"}

    def test_user_cant_retrieve(self, user_client):
        token = PreAuthTokenGenerator().make_token(user_client.user)
        r = user_client.post(self.reverse(), data=dict(token=token))
        h.responseForbidden(r)

    def test_guest_can_authenticate(self, client):
        user = UserFactory()
        token = PreAuthTokenGenerator().make_token(user)
        r = client.post(self.reverse(), data=dict(token=token))
        h.responseOk(r)
        self.assert_token_response(r)

    @override_settings(BA_AUTH_PRE_AUTH_TOKEN_EXPIRATION_TIME_DELTA=timedelta(days=1))
    def test_guest_cant_authenticate_with_expired_token(self, client):
        user = UserFactory()
        token = PreAuthTokenGenerator().make_token(user)
        with freeze_time((timezone.now() + timezone.timedelta(days=2)).strftime("%Y-%m-%d")):
            r = client.post(self.reverse(), data=dict(token=token))
            h.responseBadRequest(r)


class TestPreAuthAuthToken(TestPreAuthMixin):
    view_name = "pre_auth-auth-token"

    def assert_token_response(self, r):
        assert r.data.get("token") is not None

    def test_user_cant_retrieve(self, user_client):
        token = PreAuthTokenGenerator().make_token(user_client.user)
        r = user_client.post(self.reverse(), data=dict(token=token))
        h.responseForbidden(r)

    def test_guest_can_authenticate(self, client):
        user = UserFactory()
        token = PreAuthTokenGenerator().make_token(user)
        r = client.post(self.reverse(), data=dict(token=token))
        h.responseOk(r)
        self.assert_token_response(r)

    @override_settings(BA_AUTH_PRE_AUTH_TOKEN_EXPIRATION_TIME_DELTA=timedelta(days=1))
    def test_guest_cant_authenticate_with_expired_token(self, client):
        user = UserFactory()
        token = PreAuthTokenGenerator().make_token(user)
        with freeze_time((timezone.now() + timezone.timedelta(days=2)).strftime("%Y-%m-%d")):
            r = client.post(self.reverse(), data=dict(token=token))
            h.responseBadRequest(r)
