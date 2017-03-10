from unittest.mock import patch

import pytest

from apps.base.exceptions import DeepLinkFetchError

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestReferrals(ApiMixin):
    view_name = 'referrals-list'

    @pytest.fixture
    def data(self):
        return {
            'email': 'admin@tsl.io',
        }

    def test_when_email_doesnt_exist(self, data, user_client, outbox):
        r = user_client.post(self.reverse(), data)
        h.responseOk(r)
        assert r.data['email'] == 'admin@tsl.io'
        assert len(outbox) == 1

    def test_when_email_exist(self, user_client, data, outbox):
        f.UserFactory(email=data['email'])
        with patch('apps.referrals.emails.get_deep_link') as m:
            m.return_value = {
                'url': 'https://httpbin.org/html'
            }
            r = user_client.post(self.reverse(), data)
            h.responseBadRequest(r)
            assert len(outbox) == 0

    def test_when_email_exist_actual(self, user_client, data, outbox):
        f.UserFactory(email=data['email'])
        r = user_client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert len(outbox) == 0

    def test_user_can_request_deep_link_error(self, user_client, outbox, data):
        with patch('apps.referrals.emails.get_deep_link') as m:
            m.side_effect = DeepLinkFetchError
            r = user_client.post(self.reverse(), data)
            h.responseBadRequest(r)
            assert len(outbox) == 0

    def test_sends_referrals_email(self, user_client, data):
        with patch('apps.api.v1.referrals.views.send_referrals_email') as mock:
            r = user_client.post(self.reverse(), data)
            h.responseOk(r)
            assert mock.called

    def test_when_not_a_user(self, client, data):
        with patch('apps.api.v1.referrals.views.send_referrals_email') as mock:
            f.UserFactory(email=data['email'])
            r = client.post(self.reverse(), data)
            h.responseUnauthorized(r)
            assert mock.not_called
