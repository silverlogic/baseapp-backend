import logging
from typing import Optional
from urllib.parse import urljoin

from django.apps import apps
from django.db.models import Model

from baseapp_wagtail.base.models import DefaultPageModel

logger = logging.getLogger(__name__)


class SlugAlreadyTakenError(Exception):
    """Exception raised when a slug/path is already taken by a different target."""

    pass


class WagtailURLPathSync:
    page: DefaultPageModel
    urlpath_model: Optional[Model]
    is_baseapp_pages_installed: bool

    def __init__(self, page: DefaultPageModel):
        self.page = page
        self.urlpath_model = None
        self.is_baseapp_pages_installed = apps.is_installed("baseapp_pages")
        self._load_urlpath_model()

    def _load_urlpath_model(self):
        if self.is_baseapp_pages_installed:
            from baseapp_pages.models import URLPath

            self.urlpath_model = URLPath
        else:
            self.urlpath_model = None

    def create_or_update_urlpath_draft(self):
        if not self._can_sync():
            return

        wagtail_path = self._get_wagtail_path()
        if not wagtail_path:
            return

        if self._is_path_taken_by_different_target(wagtail_path):
            raise SlugAlreadyTakenError(f"Slug '{wagtail_path}' is already taken by another page")

        try:
            live_version = self.page.url_paths.filter(is_active=True).first()
            if not live_version:
                self.page.update_url_path(
                    path=wagtail_path, language=self.page.locale.language_code, is_active=False
                )
            elif live_version.path != wagtail_path:
                if url_path := self.page.url_paths.filter(is_active=False).first():
                    url_path.path = wagtail_path
                    url_path.language = self.page.locale.language_code
                    url_path.is_active = False
                    url_path.save()
                else:
                    self.page.create_url_path(
                        path=wagtail_path, language=self.page.locale.language_code, is_active=False
                    )
        except Exception as e:
            logger.error(f"(Wagtail urlpath sync) Error creating urlpath: {e}")
            return

    def publish_urlpath(self):
        if not self._can_sync():
            return

        wagtail_path = self._get_wagtail_path()
        if not wagtail_path:
            return

        try:
            self.page.url_paths.filter(is_active=True).delete()
            self.page.update_url_path(
                path=wagtail_path, language=self.page.locale.language_code, is_active=True
            )
        except Exception as e:
            logger.error(f"(Wagtail urlpath sync) Error publishing urlpath: {e}")
            return

    def update_urlpath(self):
        if not self._can_sync():
            return

        wagtail_path = self._get_wagtail_path()
        if not wagtail_path:
            return

        try:
            self.page.update_url_path(
                path=wagtail_path, language=self.page.locale.language_code, is_active=self.page.live
            )
        except Exception as e:
            logger.error(f"(Wagtail urlpath sync) Error updating urlpath: {e}")
            return

    def deactivate_urlpath(self):
        if not self._can_sync():
            return

        try:
            self.page.deactivate_url_paths()
        except Exception as e:
            logger.error(f"(Wagtail urlpath sync) Error deactivating urlpath: {e}")
            return

    def delete_urlpath(self):
        if not self._can_sync():
            return

        try:
            self.page.delete_url_paths()
        except Exception as e:
            logger.error(f"(Wagtail urlpath sync) Error deleting urlpath: {e}")
            return

    def exists_urlpath(self, path: str) -> bool:
        if not self._can_sync():
            return False

        path = self._format_path(path)

        return self._is_path_taken_by_different_target(path)

    def _can_sync(self) -> bool:
        return (
            self.is_baseapp_pages_installed and self._is_available() and self._is_urlpath_target()
        )

    def _is_available(self) -> bool:
        return self.urlpath_model is not None

    def _is_urlpath_target(self) -> bool:
        from baseapp_pages.models import PageMixin

        return isinstance(self.page, PageMixin)

    def _is_path_taken_by_different_target(self, path: str) -> bool:
        path = self._format_path(path)

        existing_urlpath = self.urlpath_model.objects.filter(path=path).first()
        if existing_urlpath and existing_urlpath.target != self.page:
            return True

        return False

    def _format_path(self, path: str) -> str:
        if self.is_baseapp_pages_installed:
            from baseapp_pages.utils.url_path_formatter import URLPathFormatter

            return URLPathFormatter(path)()
        return path

    def _get_wagtail_path(self) -> Optional[str]:
        parent_path = self.page.get_front_url_path(self.page.get_parent())
        page_path = urljoin(parent_path, self.page.slug)
        return self._format_path(page_path)
