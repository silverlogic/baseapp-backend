from baseapp_pages.models import Metadata
from baseapp_wagtail.base.metadata.metadata_sync import WagtailMetadataSync
from baseapp_wagtail.tests.mixins import TestPageContextMixin


class MetadataSyncTests(TestPageContextMixin):
    def test_create_metadata_for_page_with_seo_fields(self):
        self.page.seo_title = "Custom SEO Title"
        self.page.search_description = "Custom description for metadata"
        self.page.save()

        sync = WagtailMetadataSync(self.page)
        result = sync.create_or_update_metadata()

        self.assertIsNotNone(result)
        self.assertEqual(result.meta_title, "Custom SEO Title")
        self.assertEqual(result.meta_description, "Custom description for metadata")
        self.assertEqual(result.meta_og_type, "article")
        self.assertEqual(result.target_object_id, self.page.id)

    def test_create_metadata_for_page_without_seo_fields(self):
        self.page.seo_title = ""
        self.page.search_description = ""
        self.page.save()

        sync = WagtailMetadataSync(self.page)
        result = sync.create_or_update_metadata()

        self.assertIsNotNone(result)
        self.assertEqual(result.meta_title, "My Page")
        self.assertIsNone(result.meta_description)
        self.assertEqual(result.meta_og_type, "article")

    def test_update_existing_metadata(self):
        self.page.seo_title = "Original Title"
        self.page.save()

        sync = WagtailMetadataSync(self.page)
        original_metadata = sync.create_or_update_metadata()

        self.page.seo_title = "Updated Title"
        self.page.search_description = "New description"
        self.page.save()

        updated_metadata = sync.create_or_update_metadata()

        self.assertEqual(original_metadata.id, updated_metadata.id)
        self.assertEqual(updated_metadata.meta_title, "Updated Title")
        self.assertEqual(updated_metadata.meta_description, "New description")

    def test_delete_metadata(self):
        self.page.seo_title = "Title to be deleted"
        self.page.save()

        sync = WagtailMetadataSync(self.page)
        metadata = sync.create_or_update_metadata()
        metadata_id = metadata.id

        result = sync.delete_metadata()

        self.assertEqual(result[0], 1)
        with self.assertRaises(Metadata.DoesNotExist):
            Metadata.objects.get(id=metadata_id)

    def test_metadata_sync_through_page_publish(self):
        self.page.seo_title = "Published Page Title"
        self.page.search_description = "Published page description"

        revision = self.page.save_revision()
        revision.publish()

        metadata = Metadata.objects.filter(target_object_id=self.page.id).first()

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.meta_title, "Published Page Title")
        self.assertEqual(metadata.meta_description, "Published page description")

    def test_metadata_sync_updates_on_republish(self):
        self.page.seo_title = "First Title"
        revision1 = self.page.save_revision()
        revision1.publish()

        metadata = Metadata.objects.get(target_object_id=self.page.id)
        self.assertEqual(metadata.meta_title, "First Title")

        self.page.seo_title = "Second Title"
        revision2 = self.page.save_revision()
        revision2.publish()

        metadata.refresh_from_db()
        self.assertEqual(metadata.meta_title, "Second Title")

        self.assertEqual(Metadata.objects.filter(target_object_id=self.page.id).count(), 1)

    def test_metadata_includes_language_from_page_locale(self):
        sync = WagtailMetadataSync(self.page)
        metadata = sync.create_or_update_metadata()

        if hasattr(self.page, "locale"):
            self.assertEqual(metadata.language, self.page.locale.language_code)
        else:
            self.assertIsNone(metadata.language)
