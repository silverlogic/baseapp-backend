import pytest
from django.test import TestCase
from freezegun import freeze_time

from baseapp_social_auth.cache.models import SocialAuthAccessTokenCache
from baseapp_social_auth.cache.tasks import clean_up_social_auth_cache

pytestmark = pytest.mark.django_db


class TestCleanUpSocialAuthCache(TestCase):
    def test_deletes_older_than_1h(self):
        with freeze_time("2022-11-01 10:00:00"):
            SocialAuthAccessTokenCache.objects.create(access_token="token1")
        with freeze_time("2022-11-01 11:00:01"):
            clean_up_social_auth_cache()
        assert SocialAuthAccessTokenCache.objects.all().exists() is False

    def test_keep_not_older_than_1h(self):
        with freeze_time("2022-11-01 10:00:00"):
            SocialAuthAccessTokenCache.objects.create(access_token="token1")
        with freeze_time("2022-11-01 10:59:59"):
            clean_up_social_auth_cache()
        assert SocialAuthAccessTokenCache.objects.all().exists()
