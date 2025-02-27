from django.urls import reverse
from rest_framework import status

from baseapp_wagtail.tests.mixins import StandardPageContextMixin
from baseapp_wagtail.tests.models import PageForTests


class PagesSitemapAPIViewSetTests(StandardPageContextMixin):
    def test_sitemap_pages(self):
        new_page = self._add_page()
        new_page.save_revision().publish()
        response = self.client.get(
            reverse("baseappwagtailapi_base:sitemap/pages:listing"),
            {"fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self._has_page(response.json(), new_page.id))
        for page in response.json():
            if page["id"] == new_page.id:
                self.assertIsNotNone(page["type"])
                self.assertIsNotNone(page["title"])
                self.assertIsNotNone(page["url_path"])
                self.assertIsNotNone(page["locale"])
                self.assertIsNotNone(page["last_published_at"])

    def test_sitemap_pages_with_unpublished_page(self):
        new_page = self._add_page()
        response = self.client.get(
            reverse("baseappwagtailapi_base:sitemap/pages:listing"),
            {"fields": "*"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self._has_page(response.json(), new_page.id))

    def _add_page(self, live=False):
        new_page = PageForTests(title="My Page Child", slug="mypage-child", live=live)
        self.page.add_child(instance=new_page)
        return new_page

    def _has_page(self, pages, page_id):
        return any(page["id"] == page_id for page in pages)
