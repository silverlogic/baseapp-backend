from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class RatingsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_ratings"

    @property
    def package_name(self) -> str:
        return "baseapp_ratings"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_ratings": [
                    "baseapp_ratings.permissions.RatingsPermissionsBackend",
                ],
            },
            django_extra_settings={
                # When False, `list_ratings` denies unauthenticated users.
                "BASEAPP_RATINGS_CAN_ANONYMOUS_VIEW_RATINGS": True,
                # Optional cap on `Rate.value`. Falsy / unset means no max.
                "BASEAPP_MAX_RATING_VALUE": None,
            },
            # Graphql
            graphql_queries=[
                "baseapp_ratings.graphql.queries.RatingsQueries",
            ],
            graphql_mutations=[
                "baseapp_ratings.graphql.mutations.RatingsMutations",
            ],
            # Deps
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": "If enabled, ratings can be tied to a Profile via Rate.profile and the my_rating resolver disambiguates by Profile."
                },
            ],
        )
