from django.utils import timezone

import pytest
from constance.test import override_config

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestLogin(ApiMixin):
    view_name = "login-list"

    def test_can_login(self, client):
        data = {"email": "john@doe.com", "password": "1234567890"}
        f.UserFactory(email=data["email"], password=data["password"])
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        assert set(r.data.keys()) == {"token"}

    def test_when_email_doesnt_exist(self, client):
        data = {"email": "john@doe.com", "password": "1234567890"}
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["email"] == ["Email does not exist."]

    def test_when_password_doesnt_match(self, client):
        data = {"email": "john@doe.com", "password": "1234567890"}
        f.UserFactory(email=data["email"], password="not password")
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["password"] == ["Incorrect password."]

    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    def test_can_login_with_not_expired_password(self, client):
        data = {"email": "john@doe.com", "password": "1234567890"}
        f.UserFactory(email=data["email"], password=data["password"])
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    def test_cant_login_with_expired_password(self, client):
        data = {"email": "john@doe.com", "password": "1234567890"}
        user = f.UserFactory(email=data["email"], password=data["password"])
        user.password_changed_date = timezone.now() - timezone.timedelta(days=1)
        user.save()
        r = client.post(self.reverse(), data)
        h.responseUnauthorized(r)
        assert r.data.get("password") is not None
