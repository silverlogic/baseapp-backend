from django.conf import settings

print(settings.INSTALLED_APPS)

import pytest

from baseapp_url_shortening.tests import factories as f

pytestmark = pytest.mark.django_db


class TestURLShortening:
    def test_short_url_redirects_to_full_url(self, client):
        instance = f.ShortUrlFactory()
        r = client.get(instance.short_url_path)
        assert r.status_code == 302
        assert r.url == instance.full_url
