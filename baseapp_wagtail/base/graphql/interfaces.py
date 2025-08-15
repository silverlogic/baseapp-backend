import graphene
from django.apps import apps
from grapple.types.interfaces import PageInterface

from baseapp_core.graphql.models import RelayModel

"""
Baseapp Interfaces Compatibility

Wagtail page type IDs are set at runtime, so the graphene ID field is not required by default. This
conflicts with relay.Node, which expects an ID to always be present. Since multiple baseapp
interfaces extend relay.Node, this can cause issues.

To fix this, we extend the original interfaces and explicitly resolve the ID field, as shown in
WagtailCommentsInterface. Because Wagtail page IDs always exist, this approach ensures compatibility
with relay.Node and avoids ID-related problems.

However, this approach only works when querying the page directly. When the Wagtail page is
referenced dynamically—such as via content_type and target id (e.g., as a comment target) — the
original interfaces must also be included in WagtailPageObjectType. This ensures the connection and
ID resolution work correctly in these dynamic GraphQL structures.
"""

if apps.is_installed("baseapp_comments"):
    from baseapp_comments.graphql.object_types import CommentsInterface

    class WagtailCommentsInterface(CommentsInterface):
        """
        Wagtail-specific comments interface for Wagtail page types that do not support
        relay.Node.
        """

        id = graphene.ID()

        def resolve_id(self, info, **kwargs):
            if isinstance(self, RelayModel):
                return self.id
            raise ValueError("WagtailCommentsInterface can only be used with RelayModel instances.")


class WagtailPageInterface(PageInterface):
    """
    Wagtail-specific page interface that extends Grapple's PageInterface to avoid
    conflicts with the baseapp_pages.graphql.PageInterface.
    """

    pass
