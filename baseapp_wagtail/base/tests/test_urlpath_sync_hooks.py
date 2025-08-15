from rest_framework import status

from baseapp_pages.models import URLPath
from baseapp_wagtail.tests.mixins import TestAdminActionsMixin
from baseapp_wagtail.tests.models import PageForTests


class URLPathSyncHooksTests(TestAdminActionsMixin):
    def test_urlpath_creation_on_page_create(self):
        response = self._post_new_page({"slug": "test-page-2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_page = self._get_page_by_slug("test-page-2")
        self.assertIsNotNone(new_page)

        urlpath = new_page.pages_url_path
        self.assertIsNone(urlpath)

        urlpath = URLPath.objects.get(path="/mypage/test-page-2")
        self.assertEqual(urlpath.path, "/mypage/test-page-2")
        self.assertFalse(urlpath.is_active)

    def test_urlpath_creation_on_page_create_and_publish(self):
        response = self._post_new_page({"action-publish": "action-publish", "slug": "test-page-2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_page = self._get_page_by_slug("test-page-2")
        self.assertIsNotNone(new_page)

        urlpath = new_page.pages_url_path
        self.assertIsNotNone(urlpath)
        self.assertEqual(urlpath.path, "/mypage/test-page-2")
        self.assertTrue(urlpath.is_active)

    def test_urlpath_update_on_page_publish(self):
        self.assertIsNone(self.page.pages_url_path)

        response = self._post_publish_page(self.page)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._reload_the_page()

        urlpath = self.page.pages_url_path
        self.assertTrue(urlpath.is_active)

    def test_urlpath_deactivation_on_page_unpublish(self):
        response = self._post_publish_page(self.page)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._reload_the_page()

        urlpath = self.page.pages_url_path
        self.assertTrue(urlpath.is_active)

        response = self._post_unpublish_page(self.page)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._reload_the_page()

        urlpath = self.page.pages_url_path
        self.assertIsNone(urlpath)

        urlpath = URLPath.objects.get(path="/test-page")
        self.assertFalse(urlpath.is_active)

    def test_urlpath_deletion_on_page_delete(self):
        response = self._post_new_page({"action-publish": "action-publish", "slug": "test-page-2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        page = self._get_page_by_slug("test-page-2")

        urlpath = page.pages_url_path
        self.assertTrue(urlpath.is_active)

        response = self._post_delete_page(page)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(PageForTests.objects.filter(id=page.id).exists())

        urlpath = URLPath.objects.filter(path="/mypage/test-page-2").exists()
        self.assertFalse(urlpath)

    def test_editting_page_already_published_not_changing_existing_urlpath(self):
        response = self._post_new_page({"action-publish": "action-publish", "slug": "test-page-2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        page = self._get_page_by_slug("test-page-2")

        urlpath = page.pages_url_path
        self.assertTrue(urlpath.is_active)

        edit_data = {
            "title": "Updated Page Title",
            "slug": "updated-page-slug",
        }

        response = self._post_edit_page(page, edit_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        urlpath = page.pages_url_path
        self.assertEqual(urlpath.path, "/mypage/test-page-2")

    def test_urlpath_path_update_on_page_edit(self):
        response = self._post_new_page({"action-publish": "action-publish", "slug": "test-page-2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        page = self._get_page_by_slug("test-page-2")

        urlpath = page.pages_url_path
        self.assertTrue(urlpath.is_active)

        edit_data = {
            "title": "Updated Page Title",
            "slug": "updated-page-slug",
        }

        response = self._post_publish_page(page, edit_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        urlpath = page.pages_url_path
        self.assertEqual(urlpath.path, "/mypage/updated-page-slug")
