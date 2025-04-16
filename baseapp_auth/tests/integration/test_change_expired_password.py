import time

import pytest
from constance.test import override_config
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.utils.timezone import timedelta

import baseapp_auth.tests.helpers as h
from baseapp_auth.tests.mixins import ApiMixin
from baseapp_auth.tokens import ChangeExpiredPasswordTokenGenerator

User = get_user_model()
UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


class TestChangeExpiredPasswordMixin(ApiMixin):
    def check_data_keys(self, data):
        if isinstance(data, dict):
            if set(data.keys()) == {"count", "next", "previous", "results"}:
                self.check_data_keys(data["results"])
            else:
                assert set(data.keys()) == {"detail"}
        elif isinstance(data, list):
            for element in data:
                self.check_data_keys(element)
        else:
            assert False


class TestChangeExpiredPasswordDetailMixin(TestChangeExpiredPasswordMixin):
    view_name = "change-expired-password-detail"


class TestChangeExpiredPasswordListMixin(TestChangeExpiredPasswordMixin):
    view_name = "change-expired-password-list"


class TestChangeExpiredPasswordCreate(TestChangeExpiredPasswordListMixin):
    @override_config(USER_PASSWORD_EXPIRATION_INTERVAL=1)
    @override_settings(
        BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5)
    )
    def test_can_change_expired_password_with_valid_token(self, client):
        user_data = {"email": "john@doe.com", "password": "1234567890"}
        user = UserFactory(email=user_data["email"], password=user_data["password"])
        user.password_changed_date = timezone.now() - timezone.timedelta(days=1)
        user.save()
        token = ChangeExpiredPasswordTokenGenerator().make_token(user)
        data = dict(
            current_password=user_data["password"],
            new_password=user_data["password"] + "7",
            token=token,
        )

        User.objects.get(pk=user.pk).is_password_expired is True
        r = client.post(self.reverse(), data=data)
        h.responseOk(r)
        self.check_data_keys(r.data)
        assert r.data["detail"] == "success"
        User.objects.get(pk=user.pk).is_password_expired is False

        old_password = user.password
        user.refresh_from_db()
        new_password = user.password
        assert old_password != new_password

    @override_settings(
        BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5)
    )
    def test_cant_change_expired_password_with_valid_token_and_invalid_current_password(
        self, client
    ):
        user_data = {"email": "john@doe.com", "password": "1234567890"}
        user = UserFactory(email=user_data["email"], password=user_data["password"])
        token = ChangeExpiredPasswordTokenGenerator().make_token(user)
        data = dict(
            current_password=user_data["password"] + "3",
            new_password=user_data["password"] + "7",
            token=token,
        )

        r = client.post(self.reverse(), data=data)
        h.responseUnauthorized(r)
        assert r.data["detail"].code == "authentication_failed"

        old_password = user.password
        user.refresh_from_db()
        new_password = user.password
        assert old_password == new_password

    @override_settings(
        BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5)
    )
    def test_cant_change_expired_password_with_valid_token_and_same_new_password(self, client):
        user_data = {"email": "john@doe.com", "password": "1234567890"}
        user = UserFactory(email=user_data["email"], password=user_data["password"])
        token = ChangeExpiredPasswordTokenGenerator().make_token(user)
        data = dict(
            current_password=user_data["password"], new_password=user_data["password"], token=token
        )

        r = client.post(self.reverse(), data=data)
        h.responseBadRequest(r)
        assert "new_password" in r.data

        old_password = user.password
        user.refresh_from_db()
        new_password = user.password
        assert old_password == new_password

    @override_settings(
        BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1)
    )
    def test_cant_change_expired_password_with_expired_token(self, client):
        user_data = {"email": "john@doe.com", "password": "1234567890"}
        user = UserFactory(email=user_data["email"], password=user_data["password"])
        token = ChangeExpiredPasswordTokenGenerator().make_token(user)
        data = dict(
            current_password=user_data["password"],
            new_password=user_data["password"] + "7",
            token=token,
        )

        time.sleep(1.1)

        r = client.post(self.reverse(), data=data)
        h.responseBadRequest(r)

        old_password = user.password
        user.refresh_from_db()
        new_password = user.password
        assert old_password == new_password
