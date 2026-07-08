import importlib
from unittest.mock import Mock, patch

import graphene
import pytest
from django.apps import apps as django_apps
from graphene_django.settings import graphene_settings

from baseapp.activity_log.graphql.filters import ActivityLogFilter
from baseapp_core.graphql.views import GraphQLView

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

LIST_ACTIVITY_LOG_WITH_PROFILE_FIELD_GRAPHQL = """
    query {
        activityLogs {
            edges {
                node {
                    id
                    profile {
                        id
                    }
                }
            }
        }
    }
"""

LIST_ACTIVITY_LOG_WITH_PROFILE_PK_FILTER_GRAPHQL = """
    query {
        activityLogs(profilePk: 1) {
            edges {
                node {
                    id
                }
            }
        }
    }
"""


def _build_activity_log_schema_without_profiles_branch():
    original_is_installed = django_apps.is_installed

    def _is_installed_without_profiles(app_name):
        if app_name == "baseapp_profiles":
            return False
        return original_is_installed(app_name)

    # Force re-evaluation of module-level branches for schema fields/args.
    with patch.object(django_apps, "is_installed", side_effect=_is_installed_without_profiles):
        importlib.reload(importlib.import_module("baseapp.activity_log.graphql.filters"))
        importlib.reload(importlib.import_module("baseapp.activity_log.graphql.object_types"))
        queries_module = importlib.reload(
            importlib.import_module("baseapp.activity_log.graphql.queries")
        )

    class Query(graphene.ObjectType, queries_module.ActivityLogQueries):
        pass

    return graphene.Schema(query=Query)


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestActivityLogWithoutBaseappProfiles:
    def test_profile_activity_logs_returns_empty_when_profiles_are_disabled(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ):
        response = graphql_user_client(
            PROFILE_ACTIVITY_LOG_GRAPHQL,
            variables={"nodeId": django_user_client.user.profile.relay_id},
        )
        content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["activityLogs"]["edges"] == []

    def test_activity_logs_query_hides_profile_field_when_profiles_are_disabled(
        self, with_disabled_apps, graphql_user_client
    ):
        schema = _build_activity_log_schema_without_profiles_branch()
        with (
            patch.object(graphene_settings, "SCHEMA", schema),
            patch.object(GraphQLView, "schema", schema),
        ):
            response = graphql_user_client(LIST_ACTIVITY_LOG_WITH_PROFILE_FIELD_GRAPHQL)
        content = response.json()

        assert "errors" in content
        assert any(
            "Cannot query field 'profile' on type 'ActivityLog'" in error["message"]
            for error in content["errors"]
        )

    def test_activity_logs_query_hides_profile_pk_argument_when_profiles_are_disabled(
        self, with_disabled_apps, graphql_user_client
    ):
        schema = _build_activity_log_schema_without_profiles_branch()
        with (
            patch.object(graphene_settings, "SCHEMA", schema),
            patch.object(GraphQLView, "schema", schema),
        ):
            response = graphql_user_client(LIST_ACTIVITY_LOG_WITH_PROFILE_PK_FILTER_GRAPHQL)
        content = response.json()

        assert "errors" in content
        assert any(
            "Unknown argument 'profilePk' on field 'Query.activityLogs'" in error["message"]
            for error in content["errors"]
        )

    def test_list_profile_permission_is_not_granted_when_profiles_are_disabled(
        self,
        with_disabled_apps,
        django_user_client,
    ):
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

    def test_user_name_filter_uses_user_email_without_profiles(self, with_disabled_apps):
        queryset = Mock()
        queryset.filter.return_value = queryset
        filterset = ActivityLogFilter(data={}, queryset=queryset)

        result = filterset.filter_user_name(queryset, "user_name", "foo")

        assert result is queryset
        queryset.filter.assert_called_once_with(user__email__icontains="foo")
