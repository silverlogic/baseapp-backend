import pytest

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestUsersUpdate(ApiMixin):
    view_name = 'users-detail'

    def test_user_can_update_self(self, user_client):
        r = user_client.patch(self.reverse(kwargs={'pk': user_client.user.id}))
        h.responseOk(r)

    def test_user_cant_update_other_user(self, user_client):
        other_user = f.UserFactory()
        data = {'email': 'test@email.co'}
        r = user_client.patch(self.reverse(kwargs={'pk': other_user.id}), data)
        h.responseForbidden(r)

    def test_user_cant_update_email(self, user_client):
        data = {'email': 'test@email.co'}
        user_client.patch(self.reverse(kwargs={'pk': user_client.user.id}), data)
        user_client.user.refresh_from_db()
        assert user_client.user.email != 'test@email.co'


class TestUsersMe(ApiMixin):
    view_name = 'users-me'

    def test_as_anon(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_as_user(self, client):
        user = f.UserFactory()
        client.force_authenticate(user)
        r = client.get(self.reverse())
        h.responseOk(r)


class TestUsersChangePassword(ApiMixin):
    view_name = 'users-change-password'

    @pytest.fixture
    def data(self):
        return {
            'current_password': '1234567890',
            'new_password': '0987654321'
        }

    def test_as_anon(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_change_password(self, client, data):
        user = f.UserFactory(password=data['current_password'])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    def test_password_is_set(self, client, data):
        user = f.UserFactory(password=data['current_password'])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        user.refresh_from_db()
        assert user.check_password(data['new_password'])

    def test_current_password_must_match(self, client, data):
        user = f.UserFactory(password='not current password')
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data['current_password'] == ['That is not your current password.']
