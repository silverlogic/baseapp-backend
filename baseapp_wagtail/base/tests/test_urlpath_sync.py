from baseapp_pages.models import URLPath
from baseapp_pages.tests.factories import URLPathFactory
from baseapp_wagtail.base.urlpath.urlpath_sync import WagtailURLPathSync
from baseapp_wagtail.tests.mixins import TestPageContextMixin


class TestWagtailURLPathSyncIntegration(TestPageContextMixin):
    def test_create_urlpath_creates_inactive_urlpath(self):
        self.page.live = False
        self.page.save()
        sync = WagtailURLPathSync(self.page)
        sync.create_urlpath()
        urlpath = URLPath.objects.get(path="/mypage")
        self.assertEqual(urlpath.path, "/mypage")
        self.assertFalse(urlpath.is_active)
        self.assertEqual(urlpath.target, self.page)

    def test_create_urlpath_creates_unique_path(self):
        URLPathFactory(path="/mypage", is_active=False)
        sync = WagtailURLPathSync(self.page)
        sync.create_urlpath()
        self.assertTrue(URLPath.objects.filter(path="/mypage-1").exists())

    def test_update_urlpath_sets_active(self):
        sync = WagtailURLPathSync(self.page)
        sync.create_urlpath()
        self.page.save_revision().publish()
        sync.update_urlpath()
        urlpath = URLPath.objects.get(path="/mypage")
        self.assertTrue(urlpath.is_active)

    def test_deactivate_urlpath_sets_inactive(self):
        sync = WagtailURLPathSync(self.page)
        sync.create_urlpath()
        self.page.save_revision().publish()
        sync.update_urlpath()
        sync.deactivate_urlpath()
        urlpath = URLPath.objects.get(path="/mypage")
        self.assertFalse(urlpath.is_active)

    def test_delete_urlpath_removes_urlpath(self):
        sync = WagtailURLPathSync(self.page)
        sync.create_urlpath()
        self.assertTrue(URLPath.objects.filter(path="/mypage").exists())
        sync.delete_urlpath()
        self.assertFalse(URLPath.objects.filter(path="/mypage").exists())

    def test_generate_unique_path(self):
        sync = WagtailURLPathSync(self.page)
        URLPathFactory(path="/mypage", target=self.page, is_active=False)
        URLPathFactory(path="/mypage-1", target=self.page, is_active=False)
        unique_path = sync._generate_unique_path("/mypage")
        self.assertEqual(unique_path, "/mypage-2")

    def test_can_sync_true_for_page_mixin(self):
        sync = WagtailURLPathSync(self.page)
        self.assertTrue(sync._can_sync())

    def test_can_sync_false_if_not_urlpath_target(self):
        from wagtail.models import Page

        root = Page.objects.get(id=self.root_page.id)
        plain_page = Page(title="Plain", slug="plain", depth=2, path="00010002")
        root.add_child(instance=plain_page)
        sync = WagtailURLPathSync(plain_page)
        self.assertFalse(sync._can_sync())
