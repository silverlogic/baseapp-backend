import graphene
from grapple.types.interfaces import PageInterface

from baseapp_comments.graphql.object_types import CommentsInterface
from baseapp_notifications.graphql.object_types import NotificationsInterface
from baseapp_reactions.graphql.object_types import ReactionsInterface
from baseapp_reports.graphql.object_types import ReportsInterface

# TODO: Fix in next story
# https://app.approvd.io/silverlogic/BA/stories/36399
# As per @ap, these interfaces shouldn't be necessary. They are currently necessary because
# the baseapp interfaces classes inherit from RelayNode, but they shouldn't!
#
# Also if we return -1 for resolve_id, it means we are not Relay compliant. This can cause bugs.


class WagtailCommentsInterface(CommentsInterface):
    id = graphene.ID()

    def resolve_id(self, info, **kwargs):
        return str(self.id) if self.id is not None else -1


class WagtailReactionsInterface(ReactionsInterface):
    id = graphene.ID()

    def resolve_id(self, info, **kwargs):
        return str(self.id) if self.id is not None else -1


class WagtailNotificationsInterfaceInterface(NotificationsInterface):
    id = graphene.ID()

    def resolve_id(self, info, **kwargs):
        return str(self.id) if self.id is not None else -1


class WagtailReportsInterfaceInterface(ReportsInterface):
    id = graphene.ID()

    def resolve_id(self, info, **kwargs):
        return str(self.id) if self.id is not None else -1


class WagtailPageInterface(PageInterface):
    pass
