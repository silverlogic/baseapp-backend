import pytest

from baseapp_url_shortening.tests import factories as f

pytestmark = pytest.mark.django_db


class TestURLShortening:
    def test_short_url_redirects_to_full_url(self, client) -> None:
        instance = f.ShortUrlFactory()
        r = client.get(instance.short_url_path)
        assert r.status_code == 302
        assert r.url == instance.full_url

    def test_redirect_nonexistent_short_code(self, client) -> None:
        response = client.get("/v1/c/invalid_code")
        assert response.status_code == 404

    def test_rejects_non_http_scheme(self, client) -> None:
        instance = f.ShortUrlFactory(full_url="ftp://example.com/file.txt")  # NOSONAR
        response = client.get(instance.short_url_path)
        assert response.status_code == 400
