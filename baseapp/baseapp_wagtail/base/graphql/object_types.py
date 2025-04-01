import graphene
from grapple.types.interfaces import PageInterface

from baseapp_comments.graphql.object_types import CommentsInterface


class WagtailCommentsInterface(CommentsInterface):
    id = graphene.ID()

    def resolve_id(self, info, **kwargs):
        return str(self.id) if self.id is not None else -1


class WagtailPageInterface(PageInterface):
    pass
