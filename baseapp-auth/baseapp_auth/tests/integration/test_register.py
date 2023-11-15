from unittest.mock import patch

import baseapp_auth.tests.helpers as h
import pytest
from baseapp_auth.tests.mixins import ApiMixin
from baseapp_core.exceptions import DeepLinkFetchError
from baseapp_referrals.utils import get_referral_code
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()
UserFactory = h.get_user_factory()

pytestmark = [pytest.mark.django_db, pytest.mark.referrals]

skip_if_no_referrals = pytest.mark.skipif(
    "baseapp_referrals" not in settings.INSTALLED_APPS, reason="No referrals app"
)


class TestRegister(ApiMixin):
    view_name = "register-list"

    @pytest.fixture
    def data(self):
        return {"email": "john@doe.com", "password": "1234"}

    def test_can_register(self, client, data, outbox):
        r = client.post(self.reverse(), data)
        h.responseCreated(r)
        assert User.objects.count() == 1
        assert len(outbox) == 1

    def test_user_can_request_deep_link_error(self, user_client, outbox, data):
        with patch("baseapp_auth.emails.get_deep_link") as m:
            m.side_effect = DeepLinkFetchError
            r = user_client.post(self.reverse(), data)
            h.responseCreated(r)
            assert len(outbox) == 1

    def test_sends_register_email(self, user_client, data):
        with patch("baseapp_auth.rest_framework.register.views.send_welcome_email") as mock:
            r = user_client.post(self.reverse(), data)
            h.responseCreated(r)
            assert mock.called

    def test_sets_password(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseCreated(r)
        user = User.objects.get()
        assert user.check_password(data["password"])

    def test_cant_use_duplicate_email(self, client, data):
        UserFactory(email=data["email"])
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["email"] == ["That email is already in use.  Choose another."]

    @skip_if_no_referrals
    def test_can_be_referred(self, client, data):
        referrer = UserFactory()
        data["referral_code"] = get_referral_code(referrer)
        r = client.post(self.reverse(), data)
        h.responseCreated(r)
        referee = User.objects.exclude(pk=referrer.pk).first()
        referee.referred_by

    @skip_if_no_referrals
    def test_when_referral_code_is_invalid(self, client, data):
        data["referral_code"] = "18a9sdf891203"
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["referral_code"] == ["Invalid referral code."]
