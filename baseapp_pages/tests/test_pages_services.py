from unittest.mock import patch

import pytest
from django.db import IntegrityError

import baseapp_pages.services as pages_services
from baseapp_pages.models import URLPath
from baseapp_pages.services import URLPathService

from .factories import PageFactory, URLPathFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def url_path_service() -> URLPathService:
    return URLPathService()


class TestURLPathService:
    def test_url_path_service_name(self, url_path_service: URLPathService) -> None:
        assert url_path_service.service_name == "pages.url_path"

    def test_url_path_service_is_available(self, url_path_service: URLPathService) -> None:
        assert url_path_service.is_available() is True

    def test_generate_url_path_str_returns_unchanged_when_unused(
        self, url_path_service: URLPathService
    ) -> None:
        assert url_path_service.generate_url_path_str("/unique-path") == "/unique-path"
        assert url_path_service.generate_url_path_str("no-leading-slash") == "/no-leading-slash"

    def test_generate_url_path_str_appends_suffix_when_path_taken(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()
        URLPathFactory(target=page, path="/reserved", is_active=True)

        assert url_path_service.generate_url_path_str("/reserved") == "/reserved1"

    def test_generate_url_path_str_increments_trailing_digit_when_path_taken(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()
        URLPathFactory(target=page, path="/slug1", is_active=True)

        assert url_path_service.generate_url_path_str("/slug1") == "/slug2"

    def test_generate_url_path_str_resolves_chain_of_collisions(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()
        URLPathFactory(target=page, path="/chain", is_active=True)
        URLPathFactory(target=page, path="/chain1", is_active=True)

        assert url_path_service.generate_url_path_str("/chain") == "/chain2"

    def test_generate_url_path_str_normalizes_before_collision_check(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()
        URLPathFactory(target=page, path="/slug", is_active=True)

        assert url_path_service.generate_url_path_str("slug") == "/slug1"

    def test_generate_url_path_str_increments_full_numeric_suffix_when_taken(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()
        URLPathFactory(target=page, path="/slug19", is_active=True)

        assert url_path_service.generate_url_path_str("/slug19") == "/slug20"

    def test_create_url_path_generates_unique_path_by_default(
        self, url_path_service: URLPathService
    ) -> None:
        existing_page = PageFactory()
        URLPathFactory(target=existing_page, path="/shared", is_active=True)
        new_page = PageFactory()

        created = url_path_service.create_url_path(new_page, "/shared")

        assert created.path == "/shared1"
        assert created.target == new_page
        assert new_page.url_paths.filter(path="/shared1").exists()

    def test_create_url_path_normalizes_path_when_generating(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()

        created = url_path_service.create_url_path(page, "without-leading-slash")

        assert created.path == "/without-leading-slash"

    def test_create_url_path_skips_generation_when_disabled(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()

        created = url_path_service.create_url_path(page, "/explicit-path", generate_path_str=False)

        assert created.path == "/explicit-path"

    def test_create_url_path_sets_language_and_is_active(
        self, url_path_service: URLPathService
    ) -> None:
        page = PageFactory()

        created = url_path_service.create_url_path(
            page,
            "/localized",
            language="pt",
            is_active=False,
            generate_path_str=False,
        )

        assert created.language == "pt"
        assert created.is_active is False

    def test_create_url_path_raises_integrity_error_when_path_taken_and_not_generating(
        self, url_path_service: URLPathService
    ) -> None:
        holder = PageFactory()
        URLPathFactory(target=holder, path="/taken-fixed", is_active=True)
        page = PageFactory()

        with pytest.raises(IntegrityError):
            url_path_service.create_url_path(page, "/taken-fixed", generate_path_str=False)

    def test_create_url_path_stops_after_max_attempts_on_repeated_integrity_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        url_path_service: URLPathService,
    ) -> None:
        """
        GenericRelation inserts via ``QuerySet.create`` → ``model.save(force_insert=True)``,
        not ``URLPath.objects.create``; simulate DB unique races by patching ``URLPath.save``.
        """
        page = PageFactory()
        monkeypatch.setattr(pages_services, "_MAX_UNIQUE_URL_PATH_INSERT_ATTEMPTS", 4)
        original_save = URLPath.save

        def save_force_insert_raises(self: URLPath, *args: object, **kwargs: object) -> object:
            if kwargs.get("force_insert"):
                raise IntegrityError("simulated unique violation")
            return original_save(self, *args, **kwargs)

        with (
            patch.object(URLPath, "save", save_force_insert_raises),
            pytest.raises(RuntimeError, match="Could not allocate a unique URL path"),
        ):
            url_path_service.create_url_path(page, "/any-base", generate_path_str=True)

    def test_create_url_path_retries_and_allocates_next_candidate_after_conflict(
        self,
        url_path_service: URLPathService,
    ) -> None:
        """
        Simulate a single insert race: first ``force_insert`` fails, second succeeds.
        """
        page = PageFactory()
        original_save = URLPath.save
        force_insert_attempts = 0

        def save_fail_once_on_insert(self: URLPath, *args: object, **kwargs: object) -> object:
            nonlocal force_insert_attempts
            if kwargs.get("force_insert"):
                force_insert_attempts += 1
                if force_insert_attempts == 1:
                    raise IntegrityError("simulated unique violation")
            return original_save(self, *args, **kwargs)

        with patch.object(URLPath, "save", save_fail_once_on_insert):
            created = url_path_service.create_url_path(page, "/race")

        assert force_insert_attempts == 2
        assert created.path == "/race1"
        assert page.url_paths.filter(path="/race1").exists()

    def test_create_url_path_retries_and_increments_trailing_digit_after_conflict(
        self,
        url_path_service: URLPathService,
    ) -> None:
        """
        If the conflicting base ends in a digit, retries should increment that digit.
        """
        page = PageFactory()
        original_save = URLPath.save
        force_insert_attempts = 0

        def save_fail_once_on_insert(self: URLPath, *args: object, **kwargs: object) -> object:
            nonlocal force_insert_attempts
            if kwargs.get("force_insert"):
                force_insert_attempts += 1
                if force_insert_attempts == 1:
                    raise IntegrityError("simulated unique violation")
            return original_save(self, *args, **kwargs)

        with patch.object(URLPath, "save", save_fail_once_on_insert):
            created = url_path_service.create_url_path(page, "/race1")

        assert force_insert_attempts == 2
        assert created.path == "/race2"
        assert page.url_paths.filter(path="/race2").exists()
