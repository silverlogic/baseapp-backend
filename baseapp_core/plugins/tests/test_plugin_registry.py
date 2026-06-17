import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from baseapp_core.plugins.base import BaseAppPlugin
from baseapp_core.plugins.registry import PluginRegistry


class TestPluginRegistry:
    """Test suite for PluginRegistry."""

    def test_registry_initialization(self):
        """Test that registry initializes with empty state."""
        registry = PluginRegistry()
        assert registry._initialized is False
        assert len(registry._plugins) == 0
        assert len(registry._settings_cache) == 0

    def test_load_from_installed_apps_loads_plugins(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps()

        # Should have loaded at least some plugins if they're installed
        assert registry._initialized is True
        # Check that plugins are loaded (exact count depends on INSTALLED_APPS)
        assert isinstance(registry._plugins, dict)
        assert isinstance(registry._settings_cache, dict)

    def test_load_from_installed_apps_idempotent(self):
        """Test that calling load_from_installed_apps multiple times is safe."""
        registry = PluginRegistry()
        registry.load_from_installed_apps()
        first_count = len(registry._plugins)

        registry.load_from_installed_apps()
        second_count = len(registry._plugins)

        assert first_count == second_count
        assert registry._initialized is True

    def test_load_from_installed_apps_with_empty_list_skips_all_plugins(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps(installed_apps=[])
        assert registry._initialized is True
        assert len(registry._plugins) == 0

    def test_load_from_installed_apps_with_app_list_validates_against_list(self):
        """Passing ``installed_apps`` uses that list for both inclusion and required deps."""
        registry = PluginRegistry()
        with pytest.raises(ImproperlyConfigured) as exc:
            # baseapp_auth is included but it requires baseapp_core in PackageSettings; list omits it.
            registry.load_from_installed_apps(installed_apps=["baseapp_auth"])
        assert "baseapp_core" in str(exc.value) or "validation failed" in str(exc.value).lower()

    @pytest.mark.django_db
    def test_load_from_installed_apps_with_list_loads_matching_plugins_only(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps(
            installed_apps=["baseapp_core", "baseapp_auth", "baseapp_api_key", "testproject.users"]
        )
        assert "baseapp_auth" in registry._plugins
        # Not in the explicit list → skipped
        assert "baseapp_pages" not in registry._plugins

    @pytest.mark.django_db
    def test_get_plugin_returns_plugin_when_installed(self, installed_apps_with_test_plugin):
        registry = PluginRegistry()

        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            plugin = registry.get_plugin("testproject_plugin_test_app")
            assert plugin is not None
            assert isinstance(plugin, BaseAppPlugin)
            assert plugin.name == "testproject_plugin_test_app"
            assert plugin.package_name == "testproject.plugin_test_app"

    def test_get_plugin_returns_none_when_not_installed(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps()

        plugin = registry.get_plugin("nonexistent_plugin")
        assert plugin is None

    def test_get_all_plugins_returns_list(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps()

        plugins = registry.get_all_plugins()
        assert isinstance(plugins, list)
        # All items should be BaseAppPlugin instances
        for plugin in plugins:
            assert isinstance(plugin, BaseAppPlugin)

    @pytest.mark.django_db
    def test_get_installed_apps_aggregates_from_plugins(self, installed_apps_with_test_plugin):
        """Test that get_all_installed_apps aggregates from all enabled plugins."""
        registry = PluginRegistry()

        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            installed_apps = registry.get_all_installed_apps()
            assert isinstance(installed_apps, list)
            # Should contain apps from plugins (if they add themselves)
            # Note: test plugin doesn't add itself to INSTALLED_APPS, so we check middleware instead
            middleware = registry.get("MIDDLEWARE", "test_plugin")
            assert len(middleware) > 0

    @pytest.mark.django_db
    def test_get_with_slot_returns_only_slot_entries(self, installed_apps_with_test_plugin):
        """Test that get(key, slot) returns only entries for that slot."""
        registry = PluginRegistry()

        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            # Get middleware for test_plugin slot
            middleware = registry.get("MIDDLEWARE", "test_plugin")
            assert isinstance(middleware, list)
            assert "testproject.plugin_test_app.middleware.TestMiddleware" in middleware

            # Get all middleware (no slot)
            all_middleware = registry.get("MIDDLEWARE")
            assert isinstance(all_middleware, list)
            # All middleware should include slot-specific ones
            assert len(all_middleware) >= len(middleware)
            assert "testproject.plugin_test_app.middleware.TestMiddleware" in all_middleware

    def test_get_raises_keyerror_for_unknown_key(self):
        """Test that get() raises KeyError for unknown registry keys."""
        registry = PluginRegistry()
        registry.load_from_installed_apps()

        with pytest.raises(KeyError):
            registry.get("UNKNOWN_KEY")

    @pytest.mark.django_db
    def test_get_all_django_extra_settings_merges_dicts(self, installed_apps_with_test_plugin):
        """Test that get_all_django_extra_settings merges settings from all plugins."""
        registry = PluginRegistry()

        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            settings = registry.get_all_django_extra_settings()
            assert isinstance(settings, dict)
            # Should contain test plugin's settings
            assert "TEST_PLUGIN_SETTING" in settings
            assert settings["TEST_PLUGIN_SETTING"] == "test_value"
            assert "TEST_PLUGIN_ENABLED" in settings
            assert settings["TEST_PLUGIN_ENABLED"] is True

    @pytest.mark.django_db
    def test_get_all_graphql_queries_resolves_strings(self, installed_apps_with_test_plugin):
        """Test that get_all_graphql_queries resolves string paths to classes."""
        registry = PluginRegistry()

        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            registry.load_from_installed_apps()

            queries = registry.get_all_graphql_queries()
            assert isinstance(queries, list)
            # All items should be classes, not strings
            for query in queries:
                assert not isinstance(query, str), "Query should be resolved to class, not string"

    def test_get_all_urlpatterns_resolves_callables(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps()

        urlpatterns = registry.get_all_urlpatterns()
        assert isinstance(urlpatterns, list)

    def test_get_all_v1_urlpatterns_resolves_callables(self):
        registry = PluginRegistry()
        registry.load_from_installed_apps()

        urlpatterns = registry.get_all_v1_urlpatterns()
        assert isinstance(urlpatterns, list)

    @pytest.mark.django_db
    def test_plugin_validation_passes_when_requirements_met(self, installed_apps_with_test_plugin):
        registry = PluginRegistry()

        with override_settings(INSTALLED_APPS=installed_apps_with_test_plugin):
            registry._initialized = False
            registry._plugins = {}
            registry._settings_cache = {}
            # Should not raise ImproperlyConfigured
            registry.load_from_installed_apps()

            # Plugin should be loaded
            plugin = registry.get_plugin("testproject_plugin_test_app")
            assert plugin is not None
