import pytest

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
        assert url_path_service.generate_url_path_str("no-leading-slash") == "no-leading-slash"

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
