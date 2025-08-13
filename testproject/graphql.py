import graphene
from graphene import relay
from graphene.relay.node import NodeField as RelayNodeField
from graphene_django.debug import DjangoDebug
from grapple.registry import registry

from baseapp.activity_log.graphql.queries import ActivityLogQueries
from baseapp.content_feed.graphql.mutations import ContentFeedMutations
from baseapp.content_feed.graphql.queries import ContentFeedQueries
from baseapp_blocks.graphql.mutations import BlocksMutations
from baseapp_chats.graphql.mutations import ChatsMutations
from baseapp_chats.graphql.queries import ChatsQueries
from baseapp_chats.graphql.subscriptions import ChatsSubscriptions
from baseapp_comments.graphql.mutations import CommentsMutations
from baseapp_comments.graphql.queries import CommentsQueries
from baseapp_comments.graphql.subscriptions import CommentsSubscriptions
from baseapp_core.graphql import DeleteNode
from baseapp_follows.graphql.mutations import FollowsMutations
from baseapp_notifications.graphql.mutations import NotificationsMutations
from baseapp_notifications.graphql.subscriptions import NotificationsSubscription
from baseapp_organizations.graphql.mutations import OrganizationsMutations
from baseapp_organizations.graphql.queries import OrganizationsQueries
from baseapp_pages.graphql.mutations import PagesMutations
from baseapp_pages.graphql.queries import PagesQueries
from baseapp_profiles.graphql.mutations import ProfilesMutations
from baseapp_profiles.graphql.queries import ProfilesQueries
from baseapp_ratings.graphql.mutations import RatingsMutations
from baseapp_ratings.graphql.queries import RatingsQueries
from baseapp_reactions.graphql.mutations import ReactionsMutations
from baseapp_reactions.graphql.queries import ReactionsQueries
from baseapp_reports.graphql.mutations import ReportsMutations
from baseapp_reports.graphql.queries import ReportsQueries
from baseapp_wagtail.base.graphql.mutations import WagtailMutation
from baseapp_wagtail.base.graphql.object_types import WagtailURLPathObjectType
from baseapp_wagtail.base.graphql.queries import WagtailQuery
from baseapp_wagtail.base.graphql.subscriptions import WagtailSubscription
from testproject.users.graphql.queries import UsersQueries


class Query(
    UsersQueries,
    ProfilesQueries,
    CommentsQueries,
    ActivityLogQueries,
    ReactionsQueries,
    RatingsQueries,
    PagesQueries,
    OrganizationsQueries,
    ChatsQueries,
    ContentFeedQueries,
    ReportsQueries,
    WagtailQuery,
    graphene.ObjectType,
):
    node = RelayNodeField(relay.Node)
    debug = graphene.Field(DjangoDebug, name="_debug")


class Mutation(
    ProfilesMutations,
    CommentsMutations,
    ReactionsMutations,
    ReportsMutations,
    RatingsMutations,
    FollowsMutations,
    BlocksMutations,
    PagesMutations,
    NotificationsMutations,
    OrganizationsMutations,
    ChatsMutations,
    ContentFeedMutations,
    WagtailMutation,
    graphene.ObjectType,
):
    delete_node = DeleteNode.Field()


class Subscription(
    NotificationsSubscription,
    CommentsSubscriptions,
    ChatsSubscriptions,
    WagtailSubscription,
    graphene.ObjectType,
):
    pass


schema = graphene.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    # TODO: (BA-2636) Unify this inside of the wagtail package.
    types=list(registry.models.values()) + [WagtailURLPathObjectType],
)
