import re
from unittest.mock import patch

from django.conf import settings

import pytest

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestForgotPassword(ApiMixin):
    view_name = 'forgot-password-list'

    @pytest.fixture
    def data(self):
        return {
            'email': 'admin@tsl.io',
            'fallback_url': settings.FRONT_FORGOT_PASSWORD_URL.format(token="1234123124"),
        }

    def test_when_email_doesnt_exist(self, data, client):
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data['email'] == ['Email does not exist.']

    def test_when_email_exist(self, client, data, outbox, deep_link_mock_success):
        f.UserFactory(email=data['email'])
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        assert r.data['email'] == 'admin@tsl.io'
        assert len(outbox) == 1

    def test_fetch_deep_link_error(self, client, data, outbox, deep_link_mock_error):
        f.UserFactory(email=data['email'])
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        assert r.data['email'] == 'admin@tsl.io'
        assert len(outbox) == 1

    def test_sends_reset_email(self, client, data, outbox):
        with patch('apps.api.v1.forgot_password.views.send_password_reset_email') as mock:
            f.UserFactory(email=data['email'])
            r = client.post(self.reverse(), data)
            h.responseOk(r)
            assert mock.called


class TestResetPassword(ApiMixin):
    view_name = 'reset-password-list'

    def test_cant_reset_password_with_bad_token(self, client):
        data = {'token': 'bad', 'new_password': 'blub'}
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)

    def test_can_reset_password_with_token_from_email(self, client, outbox, deep_link_mock_error):
        data = {'email': 'johnnobody@gmail.com'}
        user = f.UserFactory(email=data['email'])
        client.post(self.reverse('forgot-password-list'), data)

        message_body = outbox[0].body
        match = re.search(r'/forgot-password/(\S+)', message_body)
        assert match

        token = match.group(1)

        data = {'token': token, 'new_password': 'blub', 'confirm_new_password': 'blub'}
        r = client.post(self.reverse(), data)
        h.responseOk(r)

        user.refresh_from_db()
        assert user.check_password('blub')

    def test_cant_reset_password_after_resetting_with_samelink(self, client, outbox, deep_link_mock_error):
        data = {'email': 'johnnobody@gmail.com'}
        user = f.UserFactory(email=data['email'])
        client.post(self.reverse('forgot-password-list'), data)

        message_body = outbox[0].body
        match = re.search(r'/forgot-password/(\S+)', message_body)
        assert match

        token = match.group(1)

        data = {'token': token, 'new_password': 'blub', 'confirm_new_password': 'blub'}
        r = client.post(self.reverse(), data)
        h.responseOk(r)

        user.refresh_from_db()
        assert user.check_password('blub')

        data = {'token': token, 'new_password': 'diffpass', 'confirm_new_password': 'diffpass'}
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        user.refresh_from_db()
        assert user.check_password('blub')
