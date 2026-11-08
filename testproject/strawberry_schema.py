from baseapp_auth.strawberry.queries import UsersQueries
from baseapp_core.plugins import plugin_registry
from baseapp_core.strawberry.schema import build_schema
from baseapp_profiles.strawberry.extensions import CurrentProfileExtension

schema = build_schema(
    queries=[UsersQueries, *plugin_registry.get_all_strawberry_queries()],
    mutations=plugin_registry.get_all_strawberry_mutations(),
    types=plugin_registry.get_all_strawberry_types(),
    extensions=[CurrentProfileExtension],
)
