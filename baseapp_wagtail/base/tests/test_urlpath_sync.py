from baseapp_pages.tests.factories import URLPathFactory
from baseapp_wagtail.base.urlpath.urlpath_sync import (
    SlugAlreadyTakenError,
    WagtailURLPathSync,
)
from baseapp_wagtail.tests.mixins import TestPageContextMixin


class TestWagtailURLPathSyncIntegration(TestPageContextMixin):
    def test_create_or_update_urlpath_draft_creates_inactive_urlpath(self):
        self.page.live = False
        self.page.save()
        sync = WagtailURLPathSync(self.page)
        sync.create_or_update_urlpath_draft()

        urlpath = self.page.url_paths.filter(is_active=False).first()
        self.assertIsNotNone(urlpath)
        self.assertFalse(urlpath.is_active)
        self.assertEqual(urlpath.target, self.page)

    def test_create_or_update_urlpath_draft_raises_error_if_path_taken(self):
        other_page = self.page_model(
            title="Other Page",
            slug="otherpage",
            depth=self.site.root_page.depth + 1,
            path=f"{self.site.root_page.path}0002",
        )
        self.site.root_page.add_child(instance=other_page)

        URLPathFactory(path="/mypage", target=other_page, is_active=False)

        sync = WagtailURLPathSync(self.page)
        with self.assertRaises(SlugAlreadyTakenError):
            sync.create_or_update_urlpath_draft()

    def test_create_or_update_urlpath_draft_updates_existing_draft(self):
        sync = WagtailURLPathSync(self.page)

        sync.create_or_update_urlpath_draft()
        initial_urlpath = self.page.url_paths.filter(is_active=False).first()
        initial_path = initial_urlpath.path

        # Change page slug and create draft again
        self.page.slug = "newslug"
        self.page.save()
        sync.create_or_update_urlpath_draft()

        updated_urlpath = self.page.url_paths.filter(is_active=False).first()
        self.assertEqual(updated_urlpath.id, initial_urlpath.id)
        self.assertNotEqual(updated_urlpath.path, initial_path)

    def test_publish_urlpath_sets_active(self):
        sync = WagtailURLPathSync(self.page)

        sync.create_or_update_urlpath_draft()
        self.assertFalse(self.page.url_paths.filter(is_active=True).exists())

        sync.publish_urlpath()

        urlpath = self.page.url_paths.filter(is_active=True).first()
        self.assertIsNotNone(urlpath)
        self.assertTrue(urlpath.is_active)

    def test_publish_urlpath_deletes_old_active_paths(self):
        sync = WagtailURLPathSync(self.page)

        sync.create_or_update_urlpath_draft()
        sync.publish_urlpath()
        initial_active = self.page.url_paths.filter(is_active=True).first()

        self.page.slug = "newslug"
        self.page.save()
        sync.create_or_update_urlpath_draft()
        sync.publish_urlpath()

        self.assertFalse(self.page.url_paths.filter(id=initial_active.id, is_active=True).exists())

        new_active = self.page.url_paths.filter(is_active=True).first()
        self.assertIsNotNone(new_active)
        self.assertNotEqual(new_active.id, initial_active.id)

    def test_deactivate_urlpath_sets_inactive(self):
        sync = WagtailURLPathSync(self.page)

        sync.create_or_update_urlpath_draft()
        sync.publish_urlpath()
        self.assertTrue(self.page.url_paths.filter(is_active=True).exists())

        sync.deactivate_urlpath()

        self.assertFalse(self.page.url_paths.filter(is_active=True).exists())

    def test_delete_urlpath_removes_urlpath(self):
        sync = WagtailURLPathSync(self.page)

        sync.create_or_update_urlpath_draft()
        self.assertTrue(self.page.url_paths.exists())

        sync.delete_urlpath()

        self.assertFalse(self.page.url_paths.exists())

    def test_exists_urlpath_returns_true_if_path_taken(self):
        sync = WagtailURLPathSync(self.page)

        other_page = self.page_model(
            title="Other Page",
            slug="otherpage",
            depth=self.site.root_page.depth + 1,
            path=f"{self.site.root_page.path}0002",
        )
        self.site.root_page.add_child(instance=other_page)
        URLPathFactory(path="/mypage", target=other_page, is_active=False)

        self.assertTrue(sync.exists_urlpath("/mypage"))

    def test_exists_urlpath_returns_false_if_path_not_taken(self):
        sync = WagtailURLPathSync(self.page)

        self.assertFalse(sync.exists_urlpath("/nonexistent"))

    def test_exists_urlpath_returns_false_if_path_taken_by_same_target(self):
        sync = WagtailURLPathSync(self.page)

        URLPathFactory(path="/mypage", target=self.page, is_active=False)

        self.assertFalse(sync.exists_urlpath("/mypage"))

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

    def test_can_sync_false_if_baseapp_pages_not_installed(self):
        sync = WagtailURLPathSync(self.page)
        self.assertTrue(sync._can_sync())

    def test_get_wagtail_path_formats_path_correctly(self):
        sync = WagtailURLPathSync(self.page)
        wagtail_path = sync._get_wagtail_path()

        self.assertIsNotNone(wagtail_path)
        self.assertIn("mypage", wagtail_path)

    def test_path_formatting_uses_urlpath_formatter(self):
        sync = WagtailURLPathSync(self.page)

        formatted_path = sync._format_path("/test/path")
        self.assertEqual(formatted_path, "/test/path")  # URLPathFormatter should format this
