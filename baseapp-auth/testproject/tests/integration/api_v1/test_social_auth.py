import json
import re
from unittest.mock import patch

import httpretty
import pytest
import social_django.utils
from avatar.models import Avatar

from apps.referrals.utils import get_referral_code
from apps.users.models import User

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class SocialAuthMixin(ApiMixin):
    view_name = "social-auth-list"


class OAuth2Mixin(SocialAuthMixin):
    @pytest.fixture
    def base_data(self, use_httpretty):
        return {"code": "asdf9123", "redirect_uri": "https://example.com"}


class OAuth1Mixin(SocialAuthMixin):
    @pytest.fixture
    def base_data(self, use_httpretty):
        return {}


class TestSocialAuth(SocialAuthMixin):
    def test_cant_auth_with_invalid_provider(self, client):
        data = {"provider": "blarg"}
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert "provider" in r.data


class TestOAuth2(OAuth2Mixin):
    def test_cant_auth_without_redirect_uri(self, client, base_data, settings):
        base_data["provider"] = "facebook"
        base_data.pop("redirect_uri")
        settings.SOCIAL_AUTH_FACEBOOK_KEY = "1234"
        settings.SOCIAL_AUTH_FACEBOOK_SECRET = "1234"
        settings.AUTHENTICATION_BACKENDS = ["social_core.backends.facebook.FacebookOAuth2"]
        social_django.utils.BACKENDS = settings.AUTHENTICATION_BACKENDS
        r = client.post(self.reverse(), base_data)
        h.responseBadRequest(r)
        assert "redirect_uri" in r.data


class TestFacebookSocialAuth(OAuth2Mixin):
    @pytest.fixture
    def data(self, base_data, settings, image_base64):
        base_data["provider"] = "facebook"

        settings.SOCIAL_AUTH_FACEBOOK_KEY = "1234"
        settings.SOCIAL_AUTH_FACEBOOK_SECRET = "1234"
        settings.AUTHENTICATION_BACKENDS = ["social_core.backends.facebook.FacebookOAuth2"]
        social_django.utils.BACKENDS = settings.AUTHENTICATION_BACKENDS

        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v2.\d+/me/picture$"),
            body=image_base64,
        )

        return base_data

    @pytest.fixture
    def success_data(self, data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v3.\d+/oauth/access_token$"),
            body=json.dumps({"access_token": "1234", "token_type": "type", "expires_in": 6000}),
        )
        return data

    @pytest.fixture
    def complete_data(self, success_data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v3.\d+/me$"),
            body=json.dumps(
                {
                    "id": "1387123",
                    "first_name": "John",
                    "last_name": "Smith",
                    "email": "johnsmith@example.com",
                }
            ),
        )
        return success_data

    @pytest.fixture
    def no_email_data(self, success_data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v\d+.\d+/me$"),
            body=json.dumps({"id": "1387123", "first_name": "John", "last_name": "Smith"}),
        )
        return success_data

    @pytest.fixture
    def invalid_code_data(self, data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v3.\d+/oauth/access_token$"),
            status=400,
        )
        return data

    def test_can_auth_facebook(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)

    def test_user_is_created_with_fields_filled_in(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = User.objects.get()
        assert user.first_name == "John"
        assert user.last_name == "Smith"
        assert user.email == "johnsmith@example.com"

    def test_user_avatar_is_created_from_profile_picture(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        assert Avatar.objects.count()

    def test_can_be_referred(self, client, complete_data):
        referrer = f.UserFactory()
        complete_data["referral_code"] = get_referral_code(referrer)
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        referee = User.objects.exclude(pk=referrer.pk).first()
        referee.referred_by

    def test_when_referral_code_is_invalid(self, client, data):
        data["referral_code"] = "18a9sdf891203"
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["referral_code"] == ["Invalid referral code."]

    def test_when_no_email_from_provider(self, client, no_email_data):
        r = client.post(self.reverse(), no_email_data)
        h.responseBadRequest(r)
        assert r.data["email"] == "no_email_provided"

        no_email_data["email"] = "rob@example.com"
        r = client.post(self.reverse(), no_email_data)
        h.responseOk(r)
        user = User.objects.get()
        assert user.email == "rob@example.com"

    def test_when_email_already_belongs_to_another_user(self, client, complete_data):
        f.UserFactory(email="johnsmith@example.com")
        r = client.post(self.reverse(), complete_data)
        h.responseBadRequest(r)
        assert r.data["email"] == "email_already_in_use"

    def test_when_invalid_code(self, client, invalid_code_data):
        r = client.post(self.reverse(), invalid_code_data)
        h.responseBadRequest(r)
        assert r.data["non_field_errors"] == "invalid_credentials"

    def test_is_new_response_field(self, client, complete_data):
        # Register
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        assert r.data["is_new"]

        # Login
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        assert not r.data["is_new"]


class TestTwitterSocialAuth(OAuth1Mixin):
    @pytest.fixture
    def data(self, base_data, settings):
        base_data["provider"] = "twitter"

        settings.SOCIAL_AUTH_TWITTER_KEY = "1234"
        settings.SOCIAL_AUTH_TWITTER_SECRET = "1234"
        settings.AUTHENTICATION_BACKENDS = ["social_core.backends.twitter.TwitterOAuth"]
        social_django.utils.BACKENDS = settings.AUTHENTICATION_BACKENDS

        return base_data

    @pytest.fixture
    def step1_data(self, data):
        httpretty.register_uri(
            httpretty.POST, "https://api.twitter.com/oauth/request_token", body=""
        )
        return data

    @pytest.fixture
    def step2_data(self, data):
        data["oauth_token"] = "1234"
        data["oauth_token_secret"] = "1234xyz"
        data["oauth_verifier"] = "12345"
        data["email"] = "seancook@example.com"

        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://api.twitter.com/1.\d+/account/verify_credentials.json"),
            body=json.dumps({"id": 543, "name": "Sean Cook", "screen_name": "thecooker"}),
        )

        with patch("social_core.backends.twitter.TwitterOAuth.get_unauthorized_token") as mock:
            with patch("social_core.backends.twitter.TwitterOAuth.access_token") as mock:
                mock.return_value = "1234"
                yield data

    @pytest.fixture
    def step2_data_with_profile_image(self, data, image_base64):
        data["oauth_token"] = "1234"
        data["oauth_token_secret"] = "1234xyz"
        data["oauth_verifier"] = "12345"
        data["email"] = "seancook@example.com"

        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://api.twitter.com/1.\d+/account/verify_credentials.json"),
            body=json.dumps(
                {
                    "id": 543,
                    "name": "Sean Cook",
                    "screen_name": "thecooker",
                    "profile_image_url": "http://example.com/profile_images/1234431/18272_bigger.jpg",
                }
            ),
        )

        httpretty.register_uri(
            httpretty.GET,
            "http://example.com/profile_images/1234431/18272_400x400.jpg",
            body=image_base64,
        )

        with patch("social_core.backends.twitter.TwitterOAuth.get_unauthorized_token") as mock:
            with patch("social_core.backends.twitter.TwitterOAuth.access_token") as mock:
                mock.return_value = "1234"
                yield data

    @pytest.fixture
    def step2_data_with_default_profile_image(self, data, image_base64):
        data["oauth_token"] = "1234"
        data["oauth_token_secret"] = "1234xyz"
        data["oauth_verifier"] = "12345"
        data["email"] = "seancook@example.com"

        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://api.twitter.com/1.\d+/account/verify_credentials.json"),
            body=json.dumps(
                {
                    "id": 543,
                    "name": "Sean Cook",
                    "screen_name": "thecooker",
                    "profile_image_url": "http://example.com/sticky/default_profile_images/default_profile_3_bigger.png",
                }
            ),
        )

        with patch("social_core.backends.twitter.TwitterOAuth.get_unauthorized_token") as mock:
            with patch("social_core.backends.twitter.TwitterOAuth.access_token") as mock:
                mock.return_value = "1234"
                yield data

    def test_can_perform_step1(self, client, step1_data):
        r = client.post(self.reverse(), step1_data)
        h.responseOk(r)

    def test_can_perform_step2(self, client, step2_data):
        r = client.post(self.reverse(), step2_data)
        h.responseOk(r)

    def test_user_is_created_with_fields_filled_in(self, client, step2_data):
        r = client.post(self.reverse(), step2_data)
        h.responseOk(r)
        user = User.objects.get()
        assert user.first_name == "Sean"
        assert user.last_name == "Cook"
        assert user.email == "seancook@example.com"

    def test_user_avatar_is_created_from_profile_image(self, client, step2_data_with_profile_image):
        r = client.post(self.reverse(), step2_data_with_profile_image)
        h.responseOk(r)
        assert Avatar.objects.count()

    def test_user_avatar_is_not_created_when_user_has_default_profile_image(
        self, client, step2_data_with_default_profile_image
    ):
        r = client.post(self.reverse(), step2_data_with_default_profile_image)
        h.responseOk(r)
        assert not Avatar.objects.count()


class TestLinkedInSocialAuth(OAuth2Mixin):
    @pytest.fixture
    def data(self, base_data, settings, image_base64):
        base_data["provider"] = "linkedin-oauth2"

        settings.SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY = "1234"
        settings.SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET = "1234"
        settings.AUTHENTICATION_BACKENDS = ["social_core.backends.linkedin.LinkedinOAuth2"]
        social_django.utils.BACKENDS = settings.AUTHENTICATION_BACKENDS

        httpretty.register_uri(
            httpretty.GET, re.compile("https://media.licdn.com/mpr/asd/image"), body=image_base64
        )

        return base_data

    @pytest.fixture
    def success_data(self, data):
        httpretty.register_uri(
            httpretty.POST,
            re.compile("https://www.linkedin.com/oauth/v2/accessToken$"),
            body=json.dumps({"access_token": "1234", "expires_in": 6000}),
        )
        return data

    @pytest.fixture
    def complete_data(self, success_data):
        httpretty.register_uri(
            httpretty.GET,
            # re.compile("https://api.linkedin.com/v2/people/(~|%7E):(.*)"),
            re.compile("https://api.linkedin.com/v2/me$"),
            body=json.dumps(
                {
                    "emailAddress": "bobsmith@example.com",
                    "firstName": {
                        "localized": {"en_US": "Bob"},
                        "preferredLocale": {"country": "US", "language": "en"},
                    },
                    "localizedFirstName": "Bob",
                    "headline": {
                        "localized": {"en_US": "API Enthusiast at LinkedIn"},
                        "preferredLocale": {"country": "US", "language": "en"},
                    },
                    "localizedHeadline": "API Enthusiast at LinkedIn",
                    "vanityName": "bsmith",
                    "id": "yrZCpj2Z12",
                    "lastName": {
                        "localized": {"en_US": "Smith"},
                        "preferredLocale": {"country": "US", "language": "en"},
                    },
                    "localizedLastName": "Smith",
                    "profilePicture": {
                        "displayImage": "urn:li:digitalmediaAsset:C4D00AAAAbBCDEFGhiJ"
                    },
                }
            ),
        )
        return success_data

    @pytest.fixture
    def picture_data(self, success_data):
        httpretty.register_uri(
            httpretty.GET,
            re.compile("https://api.linkedin.com/v2/me$"),
            body=json.dumps(
                {
                    "emailAddress": "bobsmith@example.com",
                    "firstName": {
                        "localized": {"en_US": "Bob"},
                        "preferredLocale": {"country": "US", "language": "en"},
                    },
                    "localizedFirstName": "Bob",
                    "headline": {
                        "localized": {"en_US": "API Enthusiast at LinkedIn"},
                        "preferredLocale": {"country": "US", "language": "en"},
                    },
                    "localizedHeadline": "API Enthusiast at LinkedIn",
                    "vanityName": "bsmith",
                    "id": "yrZCpj2Z12",
                    "lastName": {
                        "localized": {"en_US": "Smith"},
                        "preferredLocale": {"country": "US", "language": "en"},
                    },
                    "localizedLastName": "Smith",
                    "profilePicture": {
                        "displayImage": "urn:li:digitalmediaAsset:C4D00AAAAbBCDEFGhiJ"
                    },
                    "pictureUrls": {
                        "_total": 1,
                        "values": ["https://media.licdn.com/mpr/asd/image"],
                    },
                }
            ),
        )
        return success_data

    def test_can_auth_linkedin(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)

    def test_user_is_created_with_fields_filled_in(self, client, complete_data):
        r = client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = User.objects.get()
        assert user.first_name == "Bob"
        assert user.last_name == "Smith"
        assert user.email == "bobsmith@example.com"

    def test_user_avatar_is_created_from_profile_picture(self, client, picture_data):
        r = client.post(self.reverse(), picture_data)
        h.responseOk(r)
        assert Avatar.objects.count()
