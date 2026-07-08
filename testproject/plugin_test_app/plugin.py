"""
Test plugin for testing the plugin architecture.

This plugin is used in unit tests to verify plugin activation/deactivation
and settings aggregation without depending on actual baseapp_* packages.
"""

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class TestPlugin(BaseAppPlugin):
    """Test plugin that contributes various settings."""

    @property
    def name(self) -> str:
        return "testproject_plugin_test_app"

    @property
    def package_name(self) -> str:
        return "testproject.plugin_test_app"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            MIDDLEWARE={
                "test_plugin": [
                    "testproject.plugin_test_app.middleware.TestMiddleware",
                ],
            },
            AUTHENTICATION_BACKENDS={
                "test_plugin": [
                    "testproject.plugin_test_app.backends.TestBackend",
                ],
            },
            GRAPHENE__MIDDLEWARE={
                "test_plugin": [
                    "testproject.plugin_test_app.graphql.middleware.TestMiddleware",
                ],
            },
            django_extra_settings={
                "TEST_PLUGIN_SETTING": "test_value",
                "TEST_PLUGIN_ENABLED": True,
            },
            required_packages=["baseapp_core"],
            optional_packages=[],
            graphql_queries=["testproject.plugin_test_app.graphql.queries.TestQueries"],
            graphql_mutations=["testproject.plugin_test_app.graphql.mutations.TestMutations"],
            graphql_subscriptions=[],
        )
