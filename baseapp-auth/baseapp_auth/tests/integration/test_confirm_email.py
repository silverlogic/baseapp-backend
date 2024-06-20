import baseapp_auth.tests.helpers as h
import pytest
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

    def test_guest_cant_request(self, client, data):
        r = client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseUnauthorized(r)

    def test_user_can_request(self, user_client, data, deep_link_mock_success):
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)

    def test_user_can_request_when_deep_link_errors(self, user_client, data, deep_link_mock_error):
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)

    def test_sets_user_is_email_verified(self, user_client, data, deep_link_mock_success):
        assert not self.user.is_email_verified
        r = user_client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert self.user.is_email_verified

    def test_confirm_email_invalid_token(self, client, data):
        data["token"] = "invalid-token"
        r = client.put(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseUnauthorized(r)

    def test_confirm_email_no_user(self, client, data):
        r = client.put(self.reverse(kwargs={"pk": self.user.pk + 1}), data)
        h.responseUnauthorized(r)


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
