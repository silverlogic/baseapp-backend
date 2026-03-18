import pytest
from django.test import override_settings

from baseapp_core.plugins.base import BaseAppPlugin, PackageDependency, PackageSettings


class TestPackageSettings:
    """Test suite for PackageSettings model."""

    def test_package_settings_defaults(self):
        """Test that PackageSettings has sensible defaults."""
        settings = PackageSettings()
        assert settings.installed_apps == []
        assert settings.authentication_backends == {}
        assert settings.middleware == {}
        assert settings.required_packages == []
        assert settings.optional_packages == []

    def test_package_settings_required_packages_accept_strings(self):
        settings = PackageSettings(required_packages=["baseapp_core"])
        assert settings.required_packages == [PackageDependency(package="baseapp_core")]

    def test_package_settings_required_packages_accept_dict_mapping(self):
        settings = PackageSettings(
            required_packages=[
                {"baseapp_core": "Shared core models and signals"},
            ]
        )
        assert settings.required_packages == [
            PackageDependency(
                package="baseapp_core",
                description="Shared core models and signals",
            )
        ]

    def test_package_settings_installed_apps(self):
        settings = PackageSettings(installed_apps=["test_app"])
        assert settings.installed_apps == ["test_app"]

    def test_package_settings_alias_installed_apps(self):
        settings = PackageSettings(INSTALLED_APPS=["test_app"])
        assert settings.installed_apps == ["test_app"]

    def test_package_settings_slotted_fields(self):
        settings = PackageSettings(middleware={"auth": ["auth.middleware.AuthMiddleware"]})
        assert settings.middleware == {"auth": ["auth.middleware.AuthMiddleware"]}

    def test_package_settings_django_extra_settings(self):
        settings = PackageSettings(django_extra_settings={"TEST_SETTING": "test_value"})
        assert settings.django_extra_settings == {"TEST_SETTING": "test_value"}

    def test_package_settings_graphql_queries(self):
        settings = PackageSettings(graphql_queries=["test.graphql.queries.TestQueries"])
        assert settings.graphql_queries == ["test.graphql.queries.TestQueries"]

    def test_package_settings_model_dump_by_alias(self):
        settings = PackageSettings(installed_apps=["test_app"])
        data = settings.model_dump(by_alias=True)
        assert "INSTALLED_APPS" in data
        assert data["INSTALLED_APPS"] == ["test_app"]


class MockPlugin(BaseAppPlugin):
    """Mock plugin for testing."""

    def __init__(self, name: str, package_name: str, required_packages: list = None):
        self._name = name
        self._package_name = package_name
        self._required_packages = required_packages or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def package_name(self) -> str:
        return self._package_name

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            installed_apps=[self._package_name],
            required_packages=self._required_packages,
        )


class TestBaseAppPlugin:
    """Test suite for BaseAppPlugin base class."""

    def test_plugin_abstract_methods(self):
        """Test that BaseAppPlugin requires abstract methods."""
        with pytest.raises(TypeError):
            # Cannot instantiate abstract class
            BaseAppPlugin()

    def test_plugin_implementation(self):
        """Test that a concrete plugin implements required methods."""
        plugin = MockPlugin("test_plugin", "test_package")
        assert plugin.name == "test_plugin"
        assert plugin.package_name == "test_package"
        assert isinstance(plugin.get_settings(), PackageSettings)

    def test_plugin_validate_no_errors_when_requirements_met(self):
        plugin = MockPlugin("test_plugin", "test_package", required_packages=["baseapp_core"])
        # baseapp_core should be installed in test environment
        errors = plugin.validate()
        assert errors == []

    @override_settings(INSTALLED_APPS=["django.contrib.contenttypes"])
    def test_plugin_validate_errors_when_requirements_not_met(self):
        plugin = MockPlugin("test_plugin", "test_package", required_packages=["missing_package"])
        errors = plugin.validate()
        assert len(errors) > 0
        assert "missing_package" in errors[0]

    @override_settings(INSTALLED_APPS=["django.contrib.contenttypes"])
    def test_plugin_validate_errors_includes_dependency_description_when_present(self):
        plugin = MockPlugin(
            "test_plugin",
            "test_package",
            required_packages=[{"missing_package": "Enable advanced permissions"}],
        )
        errors = plugin.validate()
        assert len(errors) > 0
        assert "missing_package" in errors[0]
        assert "Enable advanced permissions" in errors[0]

    def test_plugin_ready_default_implementation(self):
        """Test that ready() has a default no-op implementation."""
        plugin = MockPlugin("test_plugin", "test_package")
        # Should not raise
        plugin.ready()

    def test_plugin_settings_cached(self):
        """Test that get_settings() can be called multiple times."""
        plugin = MockPlugin("test_plugin", "test_package")
        settings1 = plugin.get_settings()
        settings2 = plugin.get_settings()

        # Should return new instances (not cached by plugin itself)
        assert settings1.installed_apps == settings2.installed_apps
        # But they are separate instances
        assert settings1 is not settings2
