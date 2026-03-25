from __future__ import annotations

import re

from django.apps import apps
from django.db import IntegrityError, transaction

from baseapp_core.plugins import SharedServiceProvider
from baseapp_pages.models import PageMixin, URLPath

_MAX_UNIQUE_URL_PATH_INSERT_ATTEMPTS: int = 20


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
        """
        Create a URLPath while handling concurrent unique path allocations safely.

        For generated paths, this method relies on database unique constraints and
        retries with deterministic suffixes on insert conflicts.
        """
        candidate_path = self._normalize_path(path) if generate_path_str else path
        attempts = 1

        while attempts <= _MAX_UNIQUE_URL_PATH_INSERT_ATTEMPTS:
            try:
                with transaction.atomic():
                    return instance.url_paths.create(
                        path=candidate_path,
                        language=language,
                        is_active=is_active,
                    )
            except IntegrityError:
                if not generate_path_str:
                    raise

                candidate_path = self._next_path_candidate(candidate_path)
                attempts += 1

        raise RuntimeError("Could not allocate a unique URL path after retrying inserts")

    def generate_url_path_str(self, increate_path_string: str) -> str:
        """
        Return a free path candidate based on current rows.

        This helper is not concurrency-safe by itself; create_url_path performs
        final conflict resolution with DB-backed insert retries.
        """
        normalized_path = self._normalize_path(increate_path_string)
        if URLPath.objects.filter(path=normalized_path).exists():
            return self.generate_url_path_str(self._next_path_candidate(normalized_path))

        return normalized_path

    def _next_path_candidate(self, path_string: str) -> str:
        normalized_path = self._normalize_path(path_string)
        match = re.match(r"^(.*?)(\d+)$", normalized_path)
        if not match:
            return f"{normalized_path}1"

        prefix, number_suffix = match.groups()
        return f"{prefix}{int(number_suffix) + 1}"

    def _normalize_path(self, path_string: str) -> str:
        return path_string if path_string.startswith("/") else f"/{path_string}"
