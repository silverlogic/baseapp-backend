import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from baseapp_profiles.graphql.queries import ProfilesQueries
from graphene import relay

from baseapp_comments.graphql.mutations import CommentsMutations
from baseapp_comments.graphql.queries import CommentsQueries
from baseapp_comments.graphql.subscriptions import CommentsSubscriptions


class Query(graphene.ObjectType, CommentsQueries, UsersQueries, ProfilesQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    CommentsMutations,
):
    delete_node = DeleteNode.Field()


class Subscription(graphene.ObjectType, CommentsSubscriptions):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
