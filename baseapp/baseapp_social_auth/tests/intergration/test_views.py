import json
import re
from unittest.mock import patch

import httpretty
import pytest
from django.contrib.auth import get_user_model
from django.urls import include, path, reverse
from rest_framework.test import APITestCase, URLPatternsTestCase

from baseapp_core.rest_framework.routers import DefaultRouter
from baseapp_core.tests import helpers as h
from baseapp_core.tests.fixtures import *  # noqa
from baseapp_social_auth.referrals import get_referral_code
from baseapp_social_auth.views import SocialAuthViewSet

pytestmark = pytest.mark.django_db


class SocialAuthViewSetMock(APITestCase, URLPatternsTestCase):
    client_class = Client
    test_router = DefaultRouter(trailing_slash=False)
    test_router.register(r"social-auth", SocialAuthViewSet, basename="social-auth")

    urlpatterns = [
        path("/", include(test_router.urls)),
    ]

    def reverse(self):
        return reverse("social-auth-list")

    def tearDown(self):
        httpretty.reset()
        super().tearDown()


@pytest.mark.usefixtures("use_httpretty")
class TestFacebookSocialAuthViewSet(SocialAuthViewSetMock):
    def base_data(self):
        return {
            "code": "asdf9123",
            "redirect_uri": "https://example.com",
            "provider": "facebook",
        }

    def data(self):
        base_data = self.base_data()

        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v\d+.\d+/me/picture$"),
            body="1234",
        )

        return base_data

    def success_data(self):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v\d+.\d+/oauth/access_token$"),
            body=json.dumps({"access_token": "1234", "token_type": "type", "expires_in": 6000}),
        )
        return self.data()

    def complete_data(self):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v\d+.\d+/me$"),
            body=json.dumps(
                {
                    "id": "1387123",
                    "first_name": "John",
                    "last_name": "Smith",
                    "email": "johnsmith@example.com",
                }
            ),
        )
        self.success_data()
        return self.data()

    def no_email_data(self):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v\d+.\d+/me$"),
            body=json.dumps({"id": "1387123", "first_name": "John", "last_name": "Smith"}),
        )
        return self.success_data()

    def invalid_code_data(self):
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://graph.facebook.com/v\d+.\d+/oauth/access_token$"),
            status=400,
        )
        return self.data()

    def test_cant_auth_without_redirect_uri(self):
        base_data = self.base_data()
        base_data["provider"] = "facebook"
        base_data.pop("redirect_uri")
        r = self.client.post(self.reverse(), base_data)
        h.responseBadRequest(r)
        assert "redirect_uri" in r.data

    def test_can_auth_facebook(self):
        r = self.client.post(self.reverse(), self.complete_data())
        h.responseOk(r)

    def test_facebook_user_is_created_with_fields_filled_in(self):
        complete_data = self.complete_data()
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.first_name == "John"
        assert user.last_name == "Smith"
        assert user.email == "johnsmith@example.com"

    def test_facebook_user_avatar_is_created_from_profile_picture(self):
        complete_data = self.complete_data()
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.profile.image

    def test_facebook_can_be_referred(self):
        referrer = get_user_model().objects.create(email="referrer@tsl.io")
        complete_data = self.complete_data()
        complete_data["referral_code"] = get_referral_code(referrer)
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        referee = get_user_model().objects.exclude(pk=referrer.pk).first()
        referee.referred_by

    def test_facebook_when_referral_code_is_invalid(self):
        data = self.data()
        data["referral_code"] = "18a9sdf891203"
        r = self.client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["referral_code"] == ["Invalid referral code."]

    def test_facebook_when_no_email_from_provider(self):
        no_email_data = self.no_email_data()
        r = self.client.post(self.reverse(), no_email_data)
        h.responseBadRequest(r)
        assert r.data["email"] == "no_email_provided"
        return "TODO"

        no_email_data["email"] = "rob@example.com"
        r = self.client.post(self.reverse(), no_email_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.email == "rob@example.com"

    def test_facebook_when_email_already_belongs_to_another_user(self):
        complete_data = self.complete_data()
        get_user_model().objects.create(email="johnsmith@example.com")
        r = self.client.post(self.reverse(), complete_data)
        h.responseBadRequest(r)
        assert r.data["email"] == "email_already_in_use"

    def test_facebook_when_invalid_code(self):
        invalid_code_data = self.invalid_code_data()
        r = self.client.post(self.reverse(), invalid_code_data)
        h.responseBadRequest(r)
        assert r.data["non_field_errors"] == "invalid_credentials"

    def test_facebook_is_new_response_field(self):
        complete_data = self.complete_data()
        # Register
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        assert r.data["is_new"]

        # Login
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        assert not r.data["is_new"]


@pytest.mark.usefixtures("use_httpretty")
class TestTwitterSocialAuth(SocialAuthViewSetMock):
    def base_data(self):
        return {}

    def data(self):
        base_data = self.base_data()
        base_data["provider"] = "twitter"

        return base_data

    def step1_data(self):
        data = self.data()
        httpretty.register_uri(
            httpretty.POST, "https://api.twitter.com/oauth/request_token", body=""
        )
        return data

    def step2_data(self):
        data = self.data()
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

    def step2_data_with_profile_image(self):
        data = self.data()
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
            body=IMAGE_BASE64,
        )

        with patch("social_core.backends.twitter.TwitterOAuth.get_unauthorized_token") as mock:
            with patch("social_core.backends.twitter.TwitterOAuth.access_token") as mock:
                mock.return_value = "1234"
                yield data

    def step2_data_with_default_profile_image(self):
        data = self.data()
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

    def test_cant_auth_with_invalid_provider(self):
        data = {"provider": "blarg"}
        r = self.client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert "provider" in r.data

    def test_twitter_can_perform_step1(self):
        step1_data = self.step1_data()
        r = self.client.post(self.reverse(), step1_data)
        h.responseOk(r)

    def test_twitter_can_perform_step2(self):
        for step2_data in self.step2_data():
            r = self.client.post(self.reverse(), step2_data)
            h.responseOk(r)

    def test_twitter_user_is_created_with_fields_filled_in(self):
        for step2_data in self.step2_data():
            r = self.client.post(self.reverse(), step2_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.first_name == "Sean"
        assert user.last_name == "Cook"
        assert user.email == "seancook@example.com"

    def test_twitter_user_avatar_is_created_from_profile_image(self):
        for step2_data_with_profile_image in self.step2_data_with_profile_image():
            r = self.client.post(self.reverse(), step2_data_with_profile_image)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.profile.image

    def test_twitter_user_avatar_is_not_created_when_user_has_default_profile_image(
        self,
    ):
        for step2_data_with_default_profile_image in self.step2_data_with_default_profile_image():
            r = self.client.post(self.reverse(), step2_data_with_default_profile_image)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert not user.profile.image


@pytest.mark.usefixtures("use_httpretty")
class TestLinkedInSocialAuth(SocialAuthViewSetMock):
    def base_data(self):
        return {
            "code": "asdf9123",
            "redirect_uri": "https://example.com",
            "provider": "linkedin-oauth2",
        }

    def data(self):
        base_data = self.base_data()

        httpretty.register_uri(
            httpretty.GET,
            re.compile("https://media.licdn.com/mpr/asd/image"),
            body=IMAGE_BASE64,
        )

        return base_data

    def success_data(self):
        data = self.data()
        httpretty.register_uri(
            httpretty.POST,
            re.compile("https://www.linkedin.com/oauth/v2/accessToken$"),
            body=json.dumps({"access_token": "1234", "expires_in": 6000}),
        )
        return data

    def complete_data(self):
        success_data = self.success_data()
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
                }
            ),
        )
        return success_data

    def picture_data(self):
        success_data = self.success_data()
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

    def test_can_auth_linkedin(self):
        complete_data = self.complete_data()
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)

    def test_linkedin_user_is_created_with_fields_filled_in(self):
        complete_data = self.complete_data()
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.first_name == "Bob"
        assert user.last_name == "Smith"
        assert user.email == "bobsmith@example.com"

    def test_linkedin_user_avatar_is_created_from_profile_picture(self):
        picture_data = self.picture_data()
        r = self.client.post(self.reverse(), picture_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.profile.image


@pytest.mark.usefixtures("use_httpretty")
class TestGoogleSocialAuthViewSet(SocialAuthViewSetMock):
    def base_data(self):
        return {
            "code": "asdf9123",
            "redirect_uri": "https://example.com",
            "provider": "google-oauth2",
        }

    def data(self):
        base_data = self.base_data()
        httpretty.register_uri(
            httpretty.GET,
            re.compile(r"https://www.googleapis.com/oauth2/v3/userinfo"),
            body=json.dumps(
                {
                    "id": "1387123",
                    "given_name": "John",
                    "family_name": "Doe",
                    "email": "johndoe@example.com",
                }
            ),
        )
        return base_data

    def success_data(self):
        httpretty.register_uri(
            httpretty.POST,
            re.compile(r"https://accounts.google.com/o/oauth2/token$"),
            body=json.dumps({"access_token": "1234", "token_type": "type", "expires_in": 6000}),
        )
        return self.data()

    def test_can_auth_google(self):
        r = self.client.post(self.reverse(), self.success_data())
        h.responseOk(r)

    def test_google_user_is_created_with_fields_filled_in(self):
        complete_data = self.success_data()
        r = self.client.post(self.reverse(), complete_data)
        h.responseOk(r)
        user = get_user_model().objects.get()
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.email == "johndoe@example.com"
