from unittest.mock import patch

import pytest

from apps.referrals.utils import get_referral_code
from apps.users.models import User

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestRegister(ApiMixin):
    view_name = 'register-list'

    @pytest.fixture
    def data(self):
        return {
            'email': 'john@doe.com',
            'password': '1234'
        }

    def test_can_register(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseCreated(r)
        assert User.objects.count() == 1

    def test_sets_password(self, client, data):
        r = client.post(self.reverse(), data)
        h.responseCreated(r)
        user = User.objects.get()
        assert user.check_password(data['password'])

    def test_cant_use_duplicate_email(self, client, data):
        f.UserFactory(email=data['email'])
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data['email'] == ['That email is already in use.  Choose another.']

    def test_sends_welcome_email(self, client, data, outbox):
        with patch('apps.api.v1.register.views.send_welcome_email') as mock:
            r = client.post(self.reverse(), data)
            h.responseCreated(r)
            assert mock.called

    def test_can_be_referred(self, client, data):
        referrer = f.UserFactory()
        data['referral_code'] = get_referral_code(referrer)
        r = client.post(self.reverse(), data)
        h.responseCreated(r)
        referee = User.objects.exclude(pk=referrer.pk).first()
        referee.referred_by

    def test_when_referral_code_is_invalid(self, client, data):
        data['referral_code'] = '18a9sdf891203'
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data['referral_code'] == ['Invalid referral code.']
