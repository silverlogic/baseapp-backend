"""
Pytest fixtures for plugin tests.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import override_settings

from baseapp_core.plugins.registry import plugin_registry


@pytest.fixture(autouse=True)
def mock_apply_pghistory_tracks():
    """
    Mock apply_pghistory_tracks to avoid errors when apps are not installed.

    This prevents pghistory from trying to create event models for apps
    that are not in INSTALLED_APPS during tests.
    """
    with patch("baseapp_core.pghelpers.apply_pghistory_tracks"):
        yield


@pytest.fixture
def minimal_installed_apps():
    """
    Fixture providing minimal INSTALLED_APPS required for plugin tests.

    Includes:
    - Django core apps (contenttypes, auth)
    - baseapp_core (required for plugin system)
    - testproject.users (required for AUTH_USER_MODEL)
    """
    return [
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "baseapp_core",
        "testproject.users",  # Required for AUTH_USER_MODEL
    ]


@pytest.fixture
def installed_apps_with_test_plugin(minimal_installed_apps):
    """
    Fixture providing INSTALLED_APPS including the test plugin.

    Adds testproject.plugin_test_app to minimal_installed_apps.
    """
    return minimal_installed_apps + ["testproject.plugin_test_app"]


def _reset_plugin_runtime_state() -> None:
    plugin_registry._initialized = False
    plugin_registry._plugins = {}
    plugin_registry._settings_cache = {}


@contextmanager
def with_disabled_apps_context(
    disabled_apps: list[str],
    swapped_models: dict[str, str] | None = None,
):
    """
    Temporarily disable app(s) and optionally override swappable models.

    Useful outside pytest fixtures, e.g. module-level `with ...` blocks in test apps.
    """
    swapped_models = swapped_models or {}
    disabled_set = set(disabled_apps)

    installed_apps = [
        app
        for app in settings.INSTALLED_APPS
        if not any(app == name or app.endswith(f".{name}") for name in disabled_set)
    ]

    with override_settings(INSTALLED_APPS=installed_apps, **swapped_models):
        _reset_plugin_runtime_state()
        plugin_registry.load_from_installed_apps()
        yield


@pytest.fixture
def with_disabled_apps(request):
    disabled_apps = request.param
    with with_disabled_apps_context(disabled_apps):
        yield
