"""
Pytest fixtures for plugin tests.
"""

from unittest.mock import patch

import pytest


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
