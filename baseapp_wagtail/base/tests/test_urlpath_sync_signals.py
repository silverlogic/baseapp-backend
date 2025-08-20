from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync
from baseapp_wagtail.tests.mixins import TestPageContextMixin


class URLPathSyncSignalsTests(TestPageContextMixin):
    def test_publish_page_creates_urlpath(self):
        self.page.save_revision().publish()
        self._reload_the_page()

        urlpath = self.page.url_paths.filter(is_active=True).first()
        self.assertIsNotNone(urlpath)
        self.assertEqual(urlpath.path, "/mypage")

    def test_publish_page_with_existing_urlpath_drafs(self):
        WagtailURLPathSync(self.page).create_or_update_urlpath_draft()
        self.assertEqual(self.page.url_paths.filter(is_active=False).count(), 1)

        self.page.save_revision().publish()
        self.assertEqual(self.page.url_paths.all().count(), 1)
