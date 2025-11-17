from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class CommentsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_comments"

    @property
    def package_name(self) -> str:
        return "baseapp_comments"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            installed_apps=[
                "baseapp_comments",
            ],
            middleware=[],
            authentication_backends=[
                "baseapp_comments.permissions.CommentsPermissionsBackend",
            ],
            env_vars={
                "BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS": {
                    "default": True,
                    "required": False,
                    "type": bool,
                    "description": "Enable notifications for comments",
                },
                "BASEAPP_COMMENTS_MAX_PINS_PER_THREAD": {
                    "default": None,
                    "required": False,
                    "type": int,
                    "description": "Maximum pinned comments per thread",
                },
            },
            django_settings={
                "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS": True,
                "BASEAPP_COMMENTS_ENABLE_GRAPHQL_SUBSCRIPTIONS": True,
            },
            required_packages=[
                "baseapp_core",
            ],
            optional_packages=[
                "baseapp_notifications",
            ],
            graphql_queries=[
                "baseapp_comments.graphql.queries.CommentsQueries",
            ],
            graphql_mutations=[
                "baseapp_comments.graphql.mutations.CommentsMutations",
            ],
            graphql_subscriptions=[
                "baseapp_comments.graphql.subscriptions.CommentsSubscriptions",
            ],
        )
