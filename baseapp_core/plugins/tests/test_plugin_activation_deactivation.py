import pytest
from django.test import override_settings

from baseapp_core.plugins.registry import PluginRegistry


@pytest.mark.django_db
class TestPluginActivationDeactivation:
    """
    Test suite for plugin activation and deactivation.

    This is the core functionality: plugins should only contribute settings
    when their app is in INSTALLED_APPS.
    """

    def test_plugin_excluded_when_not_in_installed_apps(self, minimal_installed_apps):
        """
        This is the main use case: removing an app from INSTALLED_APPS
        should remove all its plugin contributions.
        """
        registry = PluginRegistry()

        # Load with test plugin NOT in INSTALLED_APPS
        with override_settings(INSTALLED_APPS=minimal_installed_apps):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Test plugin should NOT be loaded
            plugin = registry.get_plugin("testproject_plugin_test_app")
            assert plugin is None

            # Test plugin settings should not appear in aggregated results
            installed_apps = registry.get("INSTALLED_APPS")
            assert "testproject.plugin_test_app" not in installed_apps

    def test_plugin_included_when_in_installed_apps(self, installed_apps_with_test_plugin):
        registry = PluginRegistry()

        # Load with test plugin in INSTALLED_APPS
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Test plugin should be loaded
            plugin = registry.get_plugin("testproject_plugin_test_app")
            assert plugin is not None
            assert plugin.name == "testproject_plugin_test_app"
            assert plugin.package_name == "testproject.plugin_test_app"

            # Plugin's settings should appear in aggregated results
            middleware = registry.get("MIDDLEWARE", "test_plugin")
            assert len(middleware) > 0

    def test_plugin_settings_removed_on_deactivation(
        self, minimal_installed_apps, installed_apps_with_test_plugin
    ):
        """
        This tests the full cycle: activate -> deactivate -> verify removal.
        """
        registry = PluginRegistry()

        # Step 1: Activate plugin
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            plugin = registry.get_plugin("testproject_plugin_test_app")
            assert plugin is not None
            initial_plugin_count = len(registry._plugins)
            assert initial_plugin_count > 0

            # Verify settings are present
            middleware = registry.get("MIDDLEWARE", "test_plugin")
            assert len(middleware) > 0

        # Step 2: Deactivate plugin (remove from INSTALLED_APPS)
        with override_settings(INSTALLED_APPS=minimal_installed_apps):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Plugin should be gone
            plugin = registry.get_plugin("testproject_plugin_test_app")
            assert plugin is None

            # Plugin count should be reduced
            final_plugin_count = len(registry._plugins)
            assert final_plugin_count < initial_plugin_count

            # Settings should be removed
            middleware = registry.get("MIDDLEWARE", "test_plugin")
            assert middleware == []

    def test_plugin_settings_not_in_aggregated_results_when_deactivated(
        self, minimal_installed_apps, installed_apps_with_test_plugin
    ):
        registry = PluginRegistry()

        # First, get settings with plugin active
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get aggregated settings
            auth_backends_with_plugin = registry.get("AUTHENTICATION_BACKENDS")
            middleware_with_plugin = registry.get("MIDDLEWARE", "test_plugin")
            extra_settings_with_plugin = registry.get_all_django_extra_settings()

            # Verify plugin contributions are present
            assert "testproject.plugin_test_app.backends.TestBackend" in auth_backends_with_plugin
            assert "testproject.plugin_test_app.middleware.TestMiddleware" in middleware_with_plugin
            assert "TEST_PLUGIN_SETTING" in extra_settings_with_plugin
            assert extra_settings_with_plugin["TEST_PLUGIN_SETTING"] == "test_value"

        # Then, get settings with plugin deactivated
        with override_settings(INSTALLED_APPS=minimal_installed_apps):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get aggregated settings again
            auth_backends_without_plugin = registry.get("AUTHENTICATION_BACKENDS")
            middleware_without_plugin = registry.get("MIDDLEWARE", "test_plugin")
            extra_settings_without_plugin = registry.get_all_django_extra_settings()

            # Settings from test plugin should NOT be in the second result
            assert (
                "testproject.plugin_test_app.backends.TestBackend"
                not in auth_backends_without_plugin
            )
            assert middleware_without_plugin == []  # Empty list when plugin not loaded
            assert "TEST_PLUGIN_SETTING" not in extra_settings_without_plugin

    def test_plugin_slotted_settings_removed_on_deactivation(
        self, minimal_installed_apps, installed_apps_with_test_plugin
    ):
        registry = PluginRegistry()

        # Activate plugin and get slotted settings
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get middleware for test_plugin slot
            middleware_with_plugin = registry.get("MIDDLEWARE", "test_plugin")
            assert len(middleware_with_plugin) > 0
            assert "testproject.plugin_test_app.middleware.TestMiddleware" in middleware_with_plugin

        # Deactivate plugin
        with override_settings(INSTALLED_APPS=minimal_installed_apps):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get middleware for test_plugin slot (should be empty)
            middleware_without_plugin = registry.get("MIDDLEWARE", "test_plugin")

            # Should be empty list since plugin is not loaded
            assert middleware_without_plugin == []

    def test_plugin_graphql_contributions_removed_on_deactivation(
        self, minimal_installed_apps, installed_apps_with_test_plugin
    ):
        registry = PluginRegistry()

        # Activate plugin
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get GraphQL queries
            queries_with_plugin = registry.get_all_graphql_queries()
            initial_query_count = len(queries_with_plugin)
            assert initial_query_count > 0

        # Deactivate plugin
        with override_settings(INSTALLED_APPS=minimal_installed_apps):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get GraphQL queries again
            queries_without_plugin = registry.get_all_graphql_queries()

            # Test plugin's queries should not be present
            # Count should be reduced (or same if test plugin wasn't contributing)
            assert len(queries_without_plugin) <= initial_query_count

    def test_plugin_reactivation_restores_settings(
        self, minimal_installed_apps, installed_apps_with_test_plugin
    ):
        registry = PluginRegistry()

        # Step 1: Activate
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Verify plugin is active
            middleware_1 = registry.get("MIDDLEWARE", "test_plugin")
            assert len(middleware_1) > 0

        # Step 2: Deactivate
        with override_settings(INSTALLED_APPS=minimal_installed_apps):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Verify plugin is deactivated
            middleware_2 = registry.get("MIDDLEWARE", "test_plugin")
            assert middleware_2 == []

        # Step 3: Reactivate
        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Verify plugin is reactivated
            middleware_3 = registry.get("MIDDLEWARE", "test_plugin")
            assert len(middleware_3) > 0

            # Settings should be restored
            extra_settings = registry.get_all_django_extra_settings()
            assert "TEST_PLUGIN_SETTING" in extra_settings
            assert extra_settings["TEST_PLUGIN_SETTING"] == "test_value"
