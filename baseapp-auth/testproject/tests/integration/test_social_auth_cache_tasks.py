import pytest

from apps.social_auth_cache.models import SocialAuthAccessTokenCache
from apps.social_auth_cache.tasks import clean_up_social_auth_cache

pytestmark = pytest.mark.django_db


class TestCleanUpSocialAuthCache:
    def test_it_works(self):
        SocialAuthAccessTokenCache.objects.create(access_token="asdb")
        clean_up_social_auth_cache()
