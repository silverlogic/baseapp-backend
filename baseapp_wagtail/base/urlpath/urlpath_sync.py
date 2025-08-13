from typing import Optional

from django.db.models import Model
from wagtail.models import Page


class WagtailURLPathSync:
    page: Page
    urlpath_model: Optional[Model]

    def __init__(self, page: Page):
        self.page = page
        self.urlpath_model = None
        self._load_urlpath_model()

    def _load_urlpath_model(self):
        try:
            from baseapp_pages.models import URLPath

            self.urlpath_model = URLPath
        except ImportError:
            self.urlpath_model = None

    def create_urlpath(self):
        if not self._can_sync():
            return

        wagtail_path = self._get_wagtail_path()
        if not wagtail_path:
            return

        if self.urlpath_model.objects.filter(path=wagtail_path).exists():
            wagtail_path = self._generate_unique_path(wagtail_path)

        try:
            # Use the mixin method
            self.page.create_url_path(
                path=wagtail_path, language=self.page.locale.language_code, is_active=self.page.live
            )
        except Exception:
            return

    def deactivate_urlpath(self):
        if not self._can_sync():
            return

        try:
            # Use the mixin method
            self.page.deactivate_url_paths()
        except Exception:
            return

    def update_urlpath(self):
        if not self._can_sync():
            return

        wagtail_path = self._get_wagtail_path()
        if not wagtail_path:
            return

        try:
            # Use the mixin method
            self.page.update_url_path(
                path=wagtail_path, language=self.page.locale.language_code, is_active=self.page.live
            )
        except Exception:
            return

    def delete_urlpath(self):
        if not self._can_sync():
            return

        try:
            # Use the mixin method
            self.page.delete_url_paths()
        except Exception:
            return

    def _can_sync(self) -> bool:
        return self._is_available() and self._is_urlpath_target()

    def _is_urlpath_target(self) -> bool:
        from baseapp_pages.models import PageMixin

        return isinstance(self.page, PageMixin)

    def _is_available(self) -> bool:
        return self.urlpath_model is not None

    def _get_wagtail_path(self) -> Optional[str]:
        url_parts = self.page.get_url_parts()
        if not url_parts:
            return None
        _, _, page_path = url_parts
        # TODO: (BA-2636) Add this "url formatter" in the baseapp_pages package.
        if page_path and page_path.endswith("/"):
            page_path = page_path[:-1]
        return page_path

    def _generate_unique_path(self, base_path: str) -> str:
        counter = 1
        new_path = base_path

        while self.urlpath_model.objects.filter(path=new_path).exists():
            new_path = f"{base_path}-{counter}"
            counter += 1

        return new_path
