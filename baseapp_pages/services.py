from __future__ import annotations

from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider
from baseapp_pages.models import PageMixin, URLPath


class URLPathService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "pages.url_path"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_pages")

    def create_url_path(
        self,
        instance: PageMixin,
        path: str,
        *,
        language: str | None = None,
        is_active: bool = True,
        generate_path_str: bool = True,
    ) -> URLPath:
        if generate_path_str:
            path_string = self.generate_url_path_str(path)
        else:
            path_string = path
        url_path = instance.url_paths.create(
            path=path_string, language=language, is_active=is_active
        )
        return url_path

    def generate_url_path_str(self, increate_path_string: str) -> str:
        if URLPath.objects.filter(path=increate_path_string).exists():
            path_string = (
                increate_path_string
                if increate_path_string.startswith("/")
                else f"/{increate_path_string}"
            )
            last_char = path_string[-1]
            if last_char.isdigit():
                path_string = path_string[:-1] + str(int(last_char) + 1)
            else:
                path_string = path_string + "1"

            return self.generate_url_path_str(path_string)

        return increate_path_string
