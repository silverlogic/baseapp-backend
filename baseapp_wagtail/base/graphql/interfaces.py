import graphene
from django.apps import apps
from grapple.types.interfaces import PageInterface

from baseapp_core.graphql.models import RelayModel

if apps.is_installed("baseapp_comments"):
    from baseapp_comments.graphql.object_types import CommentsInterface

    class WagtailCommentsInterface(CommentsInterface):
        """
        Wagtail-specific comments interface for Wagtail page types that do not support
        relay.Node.

        Extends baseapp_comments.graphql.CommentsInterface to enable comments on Wagtail
        pages with dynamic or non-relay-compliant id fields, avoiding relay.Node conflicts.

        If needed, an intermediate object type could be used to connect CommentsInterface.

        @see baseapp_wagtail.base.graphql.object_types.WagtailURLPathObjectType
        """

        id = graphene.ID()

        def resolve_id(self, info, **kwargs):
            if isinstance(self, RelayModel):
                return self.relay_id
            raise ValueError("WagtailCommentsInterface can only be used with RelayModel instances.")


class WagtailPageInterface(PageInterface):
    """
    Wagtail-specific page interface that extends Grapple's PageInterface to avoid
    conflicts with the baseapp_pages.graphql.PageInterface.
    """

    pass
