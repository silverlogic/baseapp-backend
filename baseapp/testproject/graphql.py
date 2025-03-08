import graphene
from baseapp_profiles.graphql.mutations import ProfilesMutations
from baseapp_profiles.graphql.queries import ProfilesQueries
from graphene import relay
from graphene.relay.node import NodeField as RelayNodeField
from graphene_django.debug import DjangoDebug

from baseapp.activity_log.graphql.queries import ActivityLogQueries
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
from baseapp_ratings.graphql.mutations import RatingsMutations
from baseapp_ratings.graphql.queries import RatingsQueries
from baseapp_reactions.graphql.mutations import ReactionsMutations
from baseapp_reactions.graphql.queries import ReactionsQueries
from baseapp_reports.graphql.mutations import ReportsMutations
from testproject.testapp.graphql.queries import UsersQueries


class Query(
    graphene.ObjectType,
    UsersQueries,
    ProfilesQueries,
    CommentsQueries,
    ActivityLogQueries,
    ReactionsQueries,
    RatingsQueries,
    PagesQueries,
    OrganizationsQueries,
    ChatsQueries,
):
    node = RelayNodeField(relay.Node)
    debug = graphene.Field(DjangoDebug, name="_debug")


class Mutation(
    graphene.ObjectType,
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
):
    delete_node = DeleteNode.Field()


class Subscription(
    graphene.ObjectType, NotificationsSubscription, CommentsSubscriptions, ChatsSubscriptions
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
