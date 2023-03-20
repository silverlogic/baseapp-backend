import graphene
from graphene import relay

from apps.comments.graphql.mutations import CommentsMutations
from apps.comments.graphql.queries import CommentsQuery
from apps.organizations.graphql.queries import ClassroomQuery
from apps.users.graphql.queries import UsersQuery


class Query(graphene.ObjectType, ClassroomQuery, CommentsQuery, UsersQuery):
    node = relay.node.NodeField(relay.Node)


class Mutation(graphene.ObjectType, CommentsMutations):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
