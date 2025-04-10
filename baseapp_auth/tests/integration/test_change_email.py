import time

import pytest
from django.test import override_settings
from django.utils.timezone import timedelta

import baseapp_auth.tests.helpers as h
from baseapp_auth.tests.mixins import ApiMixin
from baseapp_auth.tokens import (
    ChangeEmailConfirmTokenGenerator,
    ChangeEmailVerifyTokenGenerator,
)

pytestmark = pytest.mark.django_db

UserFactory = h.get_user_factory()


class TestChangeEmailRequest(ApiMixin):
    view_name = "change-email-list"

    @pytest.fixture
    def data(self):
        return {"new_email": "john@example.com"}

    def test_guest_cant_request(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseUnauthorized(r)

    def test_user_can_request(self, user_client, data, deep_link_mock_success):
        r = user_client.post(self.reverse(), data)
        h.responseOk(r)

    def test_user_can_request_when_deep_link_errors(self, user_client, data, deep_link_mock_error):
        r = user_client.post(self.reverse(), data)
        h.responseOk(r)

    def test_new_email_cant_be_in_use(self, user_client, data):
        """
        new_email holds the next email for the user, so we can't have other user
        with the same email as that new_email.
        """
        UserFactory(email=data["new_email"])
        r = user_client.post(self.reverse(), data)
        h.responseBadRequest(r)

    def test_sets_user_new_email(self, user_client, data, deep_link_mock_success):
        r = user_client.post(self.reverse(), data)
        h.responseOk(r)
        user_client.user.refresh_from_db()
        assert user_client.user.new_email == data["new_email"]

    def test_sends_an_email_to_users_current_email(
        self, user_client, data, outbox, deep_link_mock_success
    ):
        r = user_client.post(self.reverse(), data)
        h.responseOk(r)
        assert len(outbox) == 1
        assert outbox[0].to == [user_client.user.email]


class TestChangeEmailConfirm(ApiMixin):
    view_name = "change-email-confirm"

    @pytest.fixture
    def data(self):
        self.user = UserFactory(new_email="bob@example.com")
        self.url_kwargs = {"pk": self.user.pk}
        token = ChangeEmailConfirmTokenGenerator().make_token(self.user)
        return {"token": token}

    @override_settings(
        BA_AUTH_CHANGE_EMAIL_CONFIRM_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5)
    )
    def test_guest_can_confirm(self, client, data, deep_link_mock_success):
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    @override_settings(
        BA_AUTH_CHANGE_EMAIL_CONFIRM_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1)
    )
    def test_guest_cant_confirm_with_expired_token(self, client, data, deep_link_mock_success):
        time.sleep(1.1)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)

    def test_guest_can_confirm_deep_link_error(self, client, data, deep_link_mock_error):
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    def test_sets_users_is_new_email_confirmed(self, client, data, deep_link_mock_success):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert self.user.is_new_email_confirmed

    def test_sends_an_email_to_users_new_email(self, client, data, outbox, deep_link_mock_success):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert len(outbox) == 1
        assert outbox[0].to == [self.user.new_email]

    def test_when_user_doesnt_exist(self, client, data):
        r = client.post(self.reverse(kwargs={"pk": self.user.id + 1}), data)
        h.responseBadRequest(r)

    def test_when_invalid_token(self, client, data):
        data["token"] = "1234"
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)

    def test_cant_confirm_twice(self, client, data, deep_link_mock_success):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)


class TestChangeEmailVerify(ApiMixin):
    view_name = "change-email-verify"

    @pytest.fixture
    def data(self):
        self.user = UserFactory(new_email="new@example.com", is_new_email_confirmed=True)
        self.url_kwargs = {"pk": self.user.pk}
        token = ChangeEmailVerifyTokenGenerator().make_token(self.user)
        return {"token": token}

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_guest_can_verify(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_guest_cant_verify_with_expired_token(self, client, data):
        time.sleep(1.1)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_changes_users_email(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert self.user.email == "new@example.com"

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_cant_change_users_email_with_expired_token(self, client, data):
        time.sleep(1.1)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        self.user.refresh_from_db()
        assert self.user.email != "new@example.com"

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_resets_users_new_email(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert not self.user.new_email

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_dont_reset_users_new_email(self, client, data):
        time.sleep(1.1)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        self.user.refresh_from_db()
        assert self.user.new_email

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_resets_users_is_new_email_confirmed(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert not self.user.is_new_email_confirmed

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_dont_users_is_new_email_confirmed(self, client, data):
        time.sleep(1.1)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        self.user.refresh_from_db()
        assert self.user.is_new_email_confirmed

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(minutes=5))
    def test_users_is_email_verified_set(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert self.user.is_email_verified

    @override_settings(BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA=timedelta(seconds=1))
    def test_users_is_email_verified_not_set(self, client, data):
        time.sleep(1.1)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        self.user.refresh_from_db()
        assert not self.user.is_email_verified

    def test_when_user_doesnt_exist(self, client, data):
        r = client.post(self.reverse(kwargs={"pk": self.user.id + 1}), data)
        h.responseBadRequest(r)

    def test_when_invalid_token(self, client, data):
        data["token"] = "1234"
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)

    def test_cant_verify_twice(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)


class TestChangeEmailResendConfirm(ApiMixin):
    view_name = "change-email-resend-confirm"

    def test_guest_cant_resend(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_resend(self, client, outbox, deep_link_mock_success):
        user = UserFactory(new_email="new@example.com")
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseOk(r)
        assert len(outbox) == 1

    def test_user_cant_resend_if_user_has_no_new_email(self, user_client):
        r = user_client.post(self.reverse())
        h.responseBadRequest(r)

    def test_user_cant_resend_if_new_email_is_already_confirmed(self, client):
        user = UserFactory(new_email="new@example.com", is_new_email_confirmed=True)
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseBadRequest(r)


class TestChangeEmailResendVerify(ApiMixin):
    view_name = "change-email-resend-verify"

    def test_guest_cant_resend(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_resend(self, client, outbox, deep_link_mock_success):
        user = UserFactory(new_email="new@example.com", is_new_email_confirmed=True)
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseOk(r)
        assert len(outbox) == 1

    def test_user_cant_resend_if_their_new_email_is_not_confirmed(self, client):
        user = UserFactory(new_email="new@example.com", is_new_email_confirmed=False)
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseBadRequest(r)


class TestChangeEmailCancel(ApiMixin):
    view_name = "change-email-cancel"

    def test_guest_cant_cancel(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_cancel(self, client):
        user = UserFactory(new_email="new@example.com", is_new_email_confirmed=True)
        client.force_authenticate(user)
        r = client.post(self.reverse())
        h.responseOk(r)
        user.refresh_from_db()
        assert not user.new_email
        assert not user.is_new_email_confirmed
