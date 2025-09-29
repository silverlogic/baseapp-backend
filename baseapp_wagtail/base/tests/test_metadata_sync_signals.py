from unittest.mock import patch

from baseapp_wagtail.base.metadata.metadata_sync import WagtailMetadataSync
from baseapp_wagtail.tests.mixins import TestPageContextMixin


class MetadataSyncSignalsTests(TestPageContextMixin):
    def test_publish_page_creates_metadata(self):
        self.page.seo_title = "Published Page Title"
        self.page.search_description = "Published page description"
        with patch.object(WagtailMetadataSync, "_can_sync", return_value=True):
            with patch.object(WagtailMetadataSync, "create_or_update_metadata") as mock_sync:
                self.page.save_revision().publish()
                self._reload_the_page()
                mock_sync.assert_called_once()

    def test_publish_page_with_existing_metadata_updates_it(self):
        with patch.object(WagtailMetadataSync, "_can_sync", return_value=True):
            with patch.object(WagtailMetadataSync, "create_or_update_metadata") as mock_sync:
                self.page.seo_title = "Original Title"
                self.page.save_revision().publish()
                self._reload_the_page()
                self.page.seo_title = "Updated Title"
                self.page.save_revision().publish()
                self._reload_the_page()
                self.assertEqual(mock_sync.call_count, 2)

    def test_draft_page_does_not_trigger_metadata_sync(self):
        with patch.object(WagtailMetadataSync, "create_or_update_metadata") as mock_sync:
            self.page.seo_title = "Draft Title"
            self.page.save_revision()
            mock_sync.assert_not_called()

    def test_unpublish_page_deletes_metadata(self):
        with patch.object(WagtailMetadataSync, "_can_sync", return_value=True):
            with patch.object(WagtailMetadataSync, "delete_metadata") as mock_delete:
                self.page.seo_title = "Title to Unpublish"
                self.page.save_revision().publish()
                self._reload_the_page()
                self.page.unpublish()
                self._reload_the_page()
                mock_delete.assert_called_once()