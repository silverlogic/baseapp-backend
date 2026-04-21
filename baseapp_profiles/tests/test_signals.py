"""
Unit tests for baseapp_profiles.signals.

The signal handlers are tested by calling them directly with mock instances
so we are not dependent on how (or whether) the host project wires them up.
"""

from unittest.mock import MagicMock, patch

from baseapp_profiles.signals import create_profile_url_path, update_user_profile


# ---------------------------------------------------------------------------
# create_profile_url_path
# ---------------------------------------------------------------------------


def test_create_profile_url_path_ignores_updates():
    """Signal called with created=False must do nothing."""
    instance = MagicMock()
    create_profile_url_path(instance, created=False)
    instance.refresh_from_db.assert_not_called()


def test_create_profile_url_path_skips_when_pages_not_installed():
    """When baseapp_pages is not installed the handler returns early."""
    instance = MagicMock()
    with patch("baseapp_profiles.signals.apps.is_installed", return_value=False):
        create_profile_url_path(instance, created=True)
    instance.refresh_from_db.assert_not_called()


def test_create_profile_url_path_skips_url_creation_when_no_profile_id():
    """After refresh, if profile_id is still falsy, create_url_path is not called."""
    instance = MagicMock()
    instance.profile_id = None

    with patch("baseapp_profiles.signals.apps.is_installed", return_value=True):
        create_profile_url_path(instance, created=True)

    instance.refresh_from_db.assert_called_once_with(fields=["profile"])
    instance.profile.create_url_path.assert_not_called()


def test_create_profile_url_path_calls_create_url_path_when_profile_exists():
    """After refresh, if profile_id is set, create_url_path must be called."""
    instance = MagicMock()
    instance.profile_id = 42

    with patch("baseapp_profiles.signals.apps.is_installed", return_value=True):
        create_profile_url_path(instance, created=True)

    instance.refresh_from_db.assert_called_once_with(fields=["profile"])
    instance.profile.create_url_path.assert_called_once()


# ---------------------------------------------------------------------------
# update_user_profile
# ---------------------------------------------------------------------------


def test_update_user_profile_ignores_updates():
    """Signal called with created=False must do nothing."""
    instance = MagicMock()
    update_user_profile(instance, created=False)
    instance.refresh_from_db.assert_not_called()


def test_update_user_profile_returns_early_when_profile_already_exists():
    """When the DB trigger already set profile_id, no further action is taken."""
    instance = MagicMock()
    instance.first_name = "John"
    instance.last_name = "Doe"
    instance.profile_id = 99  # trigger already created the profile

    with patch("baseapp_profiles.signals.update_or_create_profile") as mock_uoc:
        update_user_profile(instance, created=True)

    instance.refresh_from_db.assert_called_once_with(fields=["profile"])
    mock_uoc.assert_not_called()


def test_update_user_profile_creates_profile_when_trigger_not_installed():
    """When no DB trigger ran (profile_id is None), the signal creates the profile."""
    instance = MagicMock()
    instance.first_name = "Jane"
    instance.last_name = "Smith"
    instance.profile_id = None  # trigger was not present

    with patch("baseapp_profiles.signals.update_or_create_profile") as mock_uoc:
        update_user_profile(instance, created=True)

    instance.refresh_from_db.assert_called_once_with(fields=["profile"])
    mock_uoc.assert_called_once_with(instance, instance, "Jane Smith")
