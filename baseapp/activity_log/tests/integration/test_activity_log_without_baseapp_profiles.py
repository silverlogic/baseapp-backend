import importlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import Mock, patch

import pytest
from django.apps import apps as django_apps

from baseapp.activity_log.filters import ActivityLogFilter
from baseapp.activity_log.strawberry.types import activity_log_interfaces

pytestmark = pytest.mark.django_db

PROFILE_ACTIVITY_LOG_GRAPHQL = """
    query ProfileActivityLog($nodeId: ID!) {
        node(id: $nodeId) {
            ... on Profile {
                activityLogs {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        }
    }
"""


def _is_installed_without_profiles(original: Callable[[str], bool]) -> Callable[[str], bool]:
    return lambda app_name: app_name != "baseapp_profiles" and original(app_name)


@contextmanager
def _reloaded_without_profiles(module_name: str) -> Iterator[ModuleType]:
    """Re-run a module's import-time `is_installed` branches, restoring the module afterwards."""
    module = importlib.import_module(module_name)
    saved = dict(module.__dict__)
    original = django_apps.is_installed
    try:
        with patch.object(
            django_apps, "is_installed", side_effect=_is_installed_without_profiles(original)
        ):
            yield importlib.reload(module)
    finally:
        module.__dict__.clear()
        module.__dict__.update(saved)


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestActivityLogWithoutBaseappProfiles:
    def test_profile_activity_logs_returns_empty_when_profiles_are_disabled(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ) -> None:
        response = graphql_user_client(
            PROFILE_ACTIVITY_LOG_GRAPHQL,
            variables={"nodeId": django_user_client.user.profile.relay_id},
        )
        content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["activityLogs"]["edges"] == []

    def test_activity_log_type_drops_profile_field_when_profiles_are_disabled(
        self, with_disabled_apps
    ) -> None:
        original = django_apps.is_installed
        with patch.object(
            django_apps, "is_installed", side_effect=_is_installed_without_profiles(original)
        ):
            assert activity_log_interfaces() == ()

    def test_activity_log_filter_drops_profile_pk_when_profiles_are_disabled(
        self, with_disabled_apps
    ) -> None:
        with _reloaded_without_profiles("baseapp.activity_log.filters") as filters:
            assert "profile_pk" not in filters.ActivityLogFilter.base_filters
        assert "profile_pk" in ActivityLogFilter.base_filters

    def test_list_profile_permission_is_not_granted_when_profiles_are_disabled(
        self,
        with_disabled_apps,
        django_user_client,
    ) -> None:
        import importlib

        importlib.reload(importlib.import_module("baseapp.activity_log.permissions"))

        from baseapp.activity_log.permissions import ActivityLogPermissionsBackend

        backend = ActivityLogPermissionsBackend()

        with patch(
            "baseapp.activity_log.permissions.apps.is_installed",
            side_effect=lambda app_name: False if app_name == "baseapp_profiles" else True,
        ):
            assert (
                backend.has_perm(
                    django_user_client.user,
                    "activity_log.list_profile_activitylog",
                    None,
                )
                is False
            )

    def test_user_name_filter_uses_user_email_without_profiles(self, with_disabled_apps) -> None:
        queryset = Mock()
        queryset.filter.return_value = queryset
        filterset = ActivityLogFilter(data={}, queryset=queryset)

        result = filterset.filter_user_name(queryset, "user_name", "foo")

        assert result is queryset
        queryset.filter.assert_called_once_with(user__email__icontains="foo")
