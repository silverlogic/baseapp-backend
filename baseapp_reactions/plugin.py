from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ReactionsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_reactions"

    @property
    def package_name(self) -> str:
        return "baseapp_reactions"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_reactions": [
                    "baseapp_reactions.permissions.ReactionsPermissionsBackend",
                ],
            },
            django_extra_settings={
                # When False, `view_reaction` denies unauthenticated users.
                "BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONS": True,
                # When True (and `baseapp_notifications` is installed), `Reaction.save`
                # fires a celery task that notifies the target's owner.
                "BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS": True,
            },
            # Graphql
            graphql_queries=[
                "baseapp_reactions.graphql.queries.ReactionsQueries",
            ],
            graphql_mutations=[
                "baseapp_reactions.graphql.mutations.ReactionsMutations",
            ],
            # Deps
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": "If enabled, reactions can be tied to a Profile via Reaction.profile and the my_reaction resolver disambiguates by Profile."
                },
                {
                    "baseapp_notifications": "If enabled and BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True, sends a notification to the target's owner on reaction creation."
                },
            ],
        )
