from importlib.metadata import entry_points

from baseapp.geo.graphql.mutations import GeoMutations
from baseapp.geo.graphql.queries import GeoQueries
from baseapp.geo.plugin import GeoPlugin
from baseapp_core.plugins.registry import PluginRegistry


class TestGeoPlugin:
    def _fresh_registry(self) -> PluginRegistry:
        registry = PluginRegistry()
        registry.load_from_installed_apps()
        return registry

    def test_entry_point_registered(self):
        eps = entry_points(group=PluginRegistry.NAMESPACE)
        geo_eps = [ep for ep in eps if ep.name == "baseapp_geo"]
        assert len(geo_eps) == 1
        assert geo_eps[0].value == "baseapp.geo.plugin:GeoPlugin"

    def test_plugin_loaded_in_registry(self):
        registry = self._fresh_registry()
        plugin = registry.get_plugin("baseapp_geo")
        assert plugin is not None
        assert isinstance(plugin, GeoPlugin)
        assert plugin.package_name == "baseapp.geo"

    def test_graphql_queries_contains_geo_queries(self):
        registry = self._fresh_registry()
        assert GeoQueries in registry.get_all_graphql_queries()

    def test_graphql_mutations_contains_geo_mutations(self):
        registry = self._fresh_registry()
        assert GeoMutations in registry.get_all_graphql_mutations()

    def test_authentication_backends_registered_under_geo_slot(self):
        registry = self._fresh_registry()
        backends = registry.get("AUTHENTICATION_BACKENDS", "baseapp_geo")
        assert backends == ["baseapp.geo.permissions.GeoPermissionsBackend"]
