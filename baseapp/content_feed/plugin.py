from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ContentFeedPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_content_feed"

    @property
    def package_name(self) -> str:
        return "baseapp.content_feed"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            graphql_queries=[
                "baseapp.content_feed.graphql.queries.ContentFeedQueries",
            ],
            graphql_mutations=[
                "baseapp.content_feed.graphql.mutations.ContentFeedMutations",
            ],
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": "If enabled, ContentPost exposes the authoring Profile via the `profile` field and ContentPostCreate sets it from the current profile."
                },
                {
                    "baseapp_reactions": "If enabled, ContentPost exposes per-post reactions count and enabled flag via the ReactableMetadataService and ReactionsInterface."
                },
                {
                    "baseapp_mentions": "If enabled, ContentPostCreate calls update_mentions to track inline @-mentions in post content."
                },
            ],
        )
