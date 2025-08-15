import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_pages.models import URLPath
from baseapp_pages.utils.url_path_formatter import URLPathFormatter

from .factories import PageFactory

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")
User = get_user_model()


def make_page_mixin_instance():
    return PageFactory()


def test_url_path_property_returns_active_path(monkeypatch):
    page = make_page_mixin_instance()
    url_path_active = page.create_url_path("/test-path", language="en", is_active=True)
    page.create_url_path("/test-path-inactive", language="en", is_active=False)

    assert page.url_path == url_path_active


def test_url_path_property_returns_none_if_no_active():
    page = make_page_mixin_instance()
    # No url paths yet
    assert page.url_path is None
    # Add only inactive
    page.create_url_path("/inactive", language="en", is_active=False)
    assert page.url_path is None


def test_create_url_path_requires_saved_instance():
    page = Page()  # not saved
    with pytest.raises(ValueError):
        page.create_url_path("/should-fail")


def test_create_url_path_creates_urlpath():
    page = make_page_mixin_instance()
    url_path = page.create_url_path("/created", language="en", is_active=True)
    assert isinstance(url_path, URLPath)
    assert url_path.path == URLPathFormatter("/created")()
    assert url_path.language == "en"
    assert url_path.is_active is True
    assert url_path.target == page


def test_update_url_path_updates_existing(monkeypatch):
    page = make_page_mixin_instance()
    url_path = page.create_url_path("/old", language="en", is_active=True)
    page.update_url_path("/new", language="fr", is_active=False)
    url_path.refresh_from_db()
    assert url_path.path == URLPathFormatter("/new")()
    assert url_path.language == "fr"
    assert url_path.is_active is False


def test_update_url_path_creates_if_none_exists():
    page = make_page_mixin_instance()
    assert page.url_path is None
    page.update_url_path("/created", language="en", is_active=True)
    url_path = page.url_path
    assert url_path is not None
    assert url_path.path == URLPathFormatter("/created")()
    assert url_path.language == "en"
    assert url_path.is_active is True


def test_deactivate_url_paths_sets_all_inactive():
    page = make_page_mixin_instance()
    page.create_url_path("/a", language="en", is_active=True)
    page.create_url_path("/b", language="fr", is_active=True)
    page.deactivate_url_paths()
    for url_path in page.url_paths.all():
        assert url_path.is_active is False


def test_delete_url_paths_deletes_all():
    page = make_page_mixin_instance()
    page.create_url_path("/a", language="en", is_active=True)
    page.create_url_path("/b", language="fr", is_active=True)
    assert page.url_paths.count() == 2
    page.delete_url_paths()
    assert page.url_paths.count() == 0
