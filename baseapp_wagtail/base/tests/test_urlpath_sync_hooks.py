from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from baseapp_wagtail.tests.mixins import TestAdminActionsMixin


class URLPathSyncHooksTests(TestAdminActionsMixin):
    def test_scheduled_publish_creates_scheduled_revision(self):
        go_live_at = timezone.now() + timedelta(hours=1)

        response = self._post_publish_page(
            self.page,
            {
                "slug": "scheduled-page",
                "go_live_at": go_live_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._reload_the_page()

        self.assertIsNotNone(self.page.scheduled_revision)
        self.assertEqual(self.page.slug, "scheduled-page")

    def test_scheduled_publish_hook_integration(self):
        go_live_at = timezone.now() + timedelta(hours=1)

        response = self._post_publish_page(
            self.page,
            {
                "slug": "hook-test-page",
                "go_live_at": go_live_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._reload_the_page()

        self.assertIsNotNone(self.page.scheduled_revision)

        urlpath_draft = self.page.url_paths.filter(is_active=False).first()
        self.assertIsNotNone(urlpath_draft)
        self.assertFalse(urlpath_draft.is_active)

    def test_scheduled_publish_hook_handles_multiple_scheduled_pages(self):
        go_live_at_1 = timezone.now() + timedelta(hours=1)
        go_live_at_2 = timezone.now() + timedelta(hours=2)

        response1 = self._post_publish_page(
            self.page,
            {
                "slug": "scheduled-page-1",
                "go_live_at": go_live_at_1.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

        response2 = self._post_publish_page(
            self.page,
            {
                "slug": "scheduled-page-2",
                "go_live_at": go_live_at_2.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        self._reload_the_page()

        self.assertIsNotNone(self.page.scheduled_revision)

        urlpath_draft = self.page.url_paths.filter(is_active=False).first()
        self.assertIsNotNone(urlpath_draft)
        self.assertFalse(urlpath_draft.is_active)
