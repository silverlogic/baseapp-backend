import json
import re

import httpretty
import pytest
import social.apps.django_app.utils
from avatar.models import Avatar

from apps.users.models import User

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class SocialAuthMixin(ApiMixin):
    view_name = 'social-auth-list'

    @pytest.fixture
    def base_data(self, use_httpretty):
        return {
            'access_token': 'asdf9123'
        }


class TestBaseSocialAuth(SocialAuthMixin):
    def test_cant_auth_with_invalid_provider(self, client, base_data):
        base_data['provider'] = 'blarg'
        r = client.post(self.reverse(), base_data)
        h.responseBadRequest(r)


class TestFacebookSocialAuth(SocialAuthMixin):
    @pytest.fixture
    def data(self, base_data, settings, image_base64):
        base_data['provider'] = 'facebook'

        settings.SOCIAL_AUTH_FACEBOOK_KEY = '1234'
        settings.SOCIAL_AUTH_FACEBOOK_SECRET = '1234'
        settings.AUTHENTICATION_BACKENDS = ['social.backends.facebook.FacebookOAuth2']
        social.apps.django_app.utils.BACKENDS = settings.AUTHENTICATION_BACKENDS

        httpretty.register_uri(
            httpretty.GET,
            re.compile('https://graph.facebook.com/v2.\d+/me/picture$'),
            body=json.dumps({
                'data': {
                    'url': 'https://example.com/picture.jpg'
                }
            })
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://example.com/picture.jpg',
            body=image_base64
        )

        return base_data

    @pytest.fixture
    def complete_data(self, data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile('https://graph.facebook.com/v2.\d+/me$'),
            body=json.dumps({
                'id': '1387123',
                'first_name': 'John',
                'last_name': 'Smith',
                'email': 'johnsmith@example.com',
            })
        )
        return data

    @pytest.fixture
    def no_email_data(self, data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile('https://graph.facebook.com/v\d+.\d+/me$'),
            body=json.dumps({
                'id': '1387123',
                'first_name': 'John',
                'last_name': 'Smith',
            })
        )
        return data

    @pytest.fixture
    def invalid_access_token_data(self, data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile('https://graph.facebook.com/v\d+.\d+/me'),
            status=400
        )
        return data

    def test_can_auth_facebook(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)

    def test_user_is_created_with_fields_filled_in(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = User.objects.get()
        assert user.first_name == 'John'
        assert user.last_name == 'Smith'
        assert user.email == 'johnsmith@example.com'

    def test_user_avatar_is_created_from_profile_picture(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        assert Avatar.objects.count()

    def test_when_no_email_from_provider(self, client, no_email_data):
        r = client.post(self.reverse(), no_email_data)
        h.responseBadRequest(r)
        assert r.data['email'] == 'no_email_provided'

        no_email_data['email'] = 'rob@example.com'
        r = client.post(self.reverse(), no_email_data)
        h.responseOk(r)
        user = User.objects.get()
        assert user.email == 'rob@example.com'

    def test_when_email_already_belongs_to_another_user(self, client, complete_data):
        f.UserFactory(email='johnsmith@example.com')
        r = client.post(self.reverse(), complete_data)
        h.responseBadRequest(r)
        assert r.data['email'] == 'email_already_in_use'

    def test_when_invalid_access_token(self, client, invalid_access_token_data):
        r = client.post(self.reverse(), invalid_access_token_data)
        h.responseBadRequest(r)
        assert 'access_token' in r.data
