import graphene
from baseapp_core.graphql import DeleteNode
from graphene import relay

from baseapp_comments.graphql.mutations import CommentsMutations
from baseapp_comments.graphql.queries import CommentsQueries
from baseapp_comments.graphql.subscriptions import CommentsSubscriptions
from testproject.testapp.graphql.queries import UsersQuery


class Query(graphene.ObjectType, CommentsQueries, UsersQuery):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    CommentsMutations,
):
    delete_node = DeleteNode.Field()


class Subscription(graphene.ObjectType, CommentsSubscriptions):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
