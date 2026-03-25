import graphene
from graphene.relay.node import NodeField as RelayNodeField
from graphene_django.debug import DjangoDebug

from baseapp.activity_log.graphql.queries import ActivityLogQueries
from baseapp.content_feed.graphql.mutations import ContentFeedMutations
from baseapp.content_feed.graphql.queries import ContentFeedQueries
from baseapp_blocks.graphql.mutations import BlocksMutations
from baseapp_chats.graphql.mutations import ChatsMutations
from baseapp_chats.graphql.queries import ChatsQueries
from baseapp_chats.graphql.subscriptions import ChatsSubscriptions
from baseapp_core.graphql import DeleteNode
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import plugin_registry
from baseapp_follows.graphql.mutations import FollowsMutations
from baseapp_notifications.graphql.mutations import NotificationsMutations
from baseapp_notifications.graphql.subscriptions import NotificationsSubscription
from baseapp_ratings.graphql.mutations import RatingsMutations
from baseapp_ratings.graphql.queries import RatingsQueries
from baseapp_reactions.graphql.mutations import ReactionsMutations
from baseapp_reactions.graphql.queries import ReactionsQueries
from baseapp_reports.graphql.mutations import ReportsMutations
from baseapp_reports.graphql.queries import ReportsQueries
from testproject.users.graphql.queries import UsersQueries

queries = plugin_registry.get_all_graphql_queries()
mutations = plugin_registry.get_all_graphql_mutations()
subscriptions = plugin_registry.get_all_graphql_subscriptions()


class Query(
    graphene.ObjectType,
    UsersQueries,
    ActivityLogQueries,
    ReactionsQueries,
    RatingsQueries,
    ChatsQueries,
    ContentFeedQueries,
    ReportsQueries,
    *queries,
):
    node = RelayNodeField(RelayNode)
    debug = graphene.Field(DjangoDebug, name="_debug")


class Mutation(
    graphene.ObjectType,
    ReactionsMutations,
    ReportsMutations,
    RatingsMutations,
    FollowsMutations,
    BlocksMutations,
    NotificationsMutations,
    ChatsMutations,
    ContentFeedMutations,
    *mutations,
):
    delete_node = DeleteNode.Field()


class Subscription(
    graphene.ObjectType,
    NotificationsSubscription,
    ChatsSubscriptions,
    *subscriptions,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
