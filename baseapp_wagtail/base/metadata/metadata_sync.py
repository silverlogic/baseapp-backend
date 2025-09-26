import logging
from typing import Optional
from django.apps import apps
from django.db.models import Model
from django.contrib.contenttypes.models import ContentType

from baseapp_wagtail.base.models import DefaultPageModel

logger = logging.getLogger(__name__)


class WagtailMetadataSync:
    page: DefaultPageModel
    metadata_model: Optional[Model]
    is_baseapp_pages_installed: bool

    def __init__(self, page: DefaultPageModel):
        self.page = page
        self.metadata_model = None
        self.is_baseapp_pages_installed = apps.is_installed("baseapp_pages")
        self._load_metadata_model()

    def _load_metadata_model(self):
        if self.is_baseapp_pages_installed:
            from baseapp_pages.models import Metadata

            self.metadata_model = Metadata
        else:
            self.metadata_model = None

    def create_or_update_metadata(self):
        if not self._can_sync():
            return

        try:
            content_type = ContentType.objects.get_for_model(self.page)
            language = (
                getattr(self.page.locale, "language_code", None)
                if hasattr(self.page, "locale")
                else None
            )

            metadata, created = self.metadata_model.objects.get_or_create(
                target_content_type=content_type,
                target_object_id=self.page.id,
                language=language,
                defaults=self._get_metadata_fields(),
            )

            if not created:
                metadata_fields = self._get_metadata_fields()
                for field, value in metadata_fields.items():
                    setattr(metadata, field, value)
                metadata.save()

            logger.info(
                f"(Wagtail metadata sync) {'Created' if created else 'Updated'} metadata for page {self.page.id}"
            )
            return metadata

        except Exception as e:
            logger.error(f"(Wagtail metadata sync) Error creating/updating metadata: {e}")
            return

    def delete_metadata(self):
        if not self._can_sync():
            return

        try:
            content_type = ContentType.objects.get_for_model(self.page)
            language = (
                getattr(self.page.locale, "language_code", None)
                if hasattr(self.page, "locale")
                else None
            )

            result = self.metadata_model.objects.filter(
                target_content_type=content_type, target_object_id=self.page.id, language=language
            ).delete()

            deleted_count, deleted_details = result
            if deleted_count > 0:
                logger.info(f"(Wagtail metadata sync) Deleted metadata for page {self.page.id}")

            return result

        except Exception as e:
            logger.error(f"(Wagtail metadata sync) Error deleting metadata: {e}")
            return

    def _get_metadata_fields(self) -> dict:
        fields = {}

        if getattr(self.page, "seo_title", None) and self.page.seo_title.strip():
            fields["meta_title"] = self.page.seo_title
        elif getattr(self.page, "title", None):
            fields["meta_title"] = self.page.title

        if getattr(self.page, "search_description", None) and self.page.search_description.strip():
            fields["meta_description"] = self.page.search_description

        social_image = None
        featured = getattr(self.page, "featured_image", None)

        if featured is not None:
            try:
                if len(featured) > 0:
                    item = featured[0]
                    struct_value = getattr(item, "value", None)
                    if struct_value is not None:
                        social_image = (
                            struct_value.get("image")
                            if hasattr(struct_value, "get")
                            else getattr(struct_value, "image", None)
                        )
            except (TypeError, IndexError, AttributeError) as e:
                logger.debug(f"Error accessing featured_image StreamField: {e}")

        if social_image:
            fields["meta_og_image"] = social_image.file
        else:
            fields["meta_og_image"] = None

        fields["meta_og_type"] = "article"
        return fields

    def _can_sync(self) -> bool:
        return (
            self.is_baseapp_pages_installed and self._is_available() and self._is_metadata_target()
        )

    def _is_available(self) -> bool:
        return self.metadata_model is not None

    def _is_metadata_target(self) -> bool:
        from baseapp_pages.models import PageMixin

        return isinstance(self.page, PageMixin)
