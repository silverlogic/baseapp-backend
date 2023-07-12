import graphene
from graphene import relay

from apps.cities.graphql.queries import CitiesQuery
from apps.comments.graphql.mutations import CommentsMutations
from apps.comments.graphql.queries import CommentsQuery
from apps.organizations.graphql.queries import ClassroomQuery
from apps.reactions.graphql.mutations import ReactionsMutations
from apps.reports.graphql.mutations import ReportsMutations
from apps.reports.graphql.queries import ReportsQuery
from apps.users.graphql.queries import UsersQuery


class Query(
    graphene.ObjectType, ClassroomQuery, CommentsQuery, UsersQuery, CitiesQuery, ReportsQuery
):
    node = relay.node.NodeField(relay.Node)


class Mutation(graphene.ObjectType, CommentsMutations, ReactionsMutations, ReportsMutations):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
