import graphene
from graphene import relay

from apps.cities.graphql.queries import CitiesQuery
from apps.comments.graphql.mutations import CommentsMutations
from apps.comments.graphql.queries import CommentsQuery
from apps.organizations.graphql.queries import ClassroomQuery
from apps.users.graphql.queries import UsersQuery


class Query(graphene.ObjectType, ClassroomQuery, CommentsQuery, UsersQuery, CitiesQuery):
    node = relay.node.NodeField(relay.Node)


class Mutation(graphene.ObjectType, CommentsMutations):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
