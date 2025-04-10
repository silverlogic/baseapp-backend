import time

import pytest
from django.test import override_settings
from django.utils.timezone import timedelta

import baseapp_auth.tests.helpers as h
from baseapp_auth.tests.mixins import ApiMixin
from baseapp_auth.tokens import ConfirmEmailTokenGenerator

pytestmark = pytest.mark.django_db

UserFactory = h.get_user_factory()


class TestConfirmEmailRequest(ApiMixin):
    view_name = "confirm-email-detail"

    @pytest.fixture
    def data(self):
        self.user = UserFactory(is_email_verified=False)
        return {"token": ConfirmEmailTokenGenerator().make_token(self.user)}

    # We're changing this from test_guest_cant_request to test_guest_can_request since we want the unlogged user to be able to confirm their email
    @override_settings(BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_guest_can_request(self, client, data):
        r = client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)

    @override_settings(BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_guest_cant_request_with_expired_token(self, client, data):
        time.sleep(1.1)
        r = client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseBadRequest(r)

    @override_settings(BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_user_can_request(self, user_client, data, deep_link_mock_success):
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)

    @override_settings(BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_user_cant_request_with_expired_token(self, user_client, data, deep_link_mock_success):
        time.sleep(1.1)
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseBadRequest(r)

    def test_user_can_request_when_deep_link_errors(self, user_client, data, deep_link_mock_error):
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)

    @override_settings(BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_sets_user_is_email_verified(self, user_client, data, deep_link_mock_success):
        assert not self.user.is_email_verified
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert self.user.is_email_verified

    @override_settings(BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_user_cant_varify_with_expired_token(self, user_client, data, deep_link_mock_success):
        assert not self.user.is_email_verified
        time.sleep(1.1)
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseBadRequest(r)
        self.user.refresh_from_db()
        assert not self.user.is_email_verified

    def test_confirm_email_invalid_token(self, client, data):
        data["token"] = "invalid-token"
        r = client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseBadRequest(r)

    def test_confirm_email_no_user(self, client, data):
        r = client.put(self.reverse(kwargs={"pk": self.user.pk + 1}), data)
        h.responseBadRequest(r)


class TestChangeEmailResendConfirm(ApiMixin):
    view_name = "confirm-email-resend-confirm"

    def test_guest_cant_resend(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_resend(self, client, outbox, deep_link_mock_success):
        user = UserFactory(is_email_verified=False)
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseOk(r)
        assert len(outbox) == 1

    def test_user_cant_resend_if_email_is_already_verified(self, client):
        user = UserFactory(is_email_verified=True)
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseBadRequest(r)
