import graphene
from apps.cities.graphql.queries import CitiesQuery
from apps.comments.graphql.mutations import CommentsMutations
from apps.comments.graphql.queries import CommentsQuery
from apps.organizations.graphql.queries import ClassroomQuery
from apps.reactions.graphql.mutations import ReactionsMutations
from apps.reports.graphql.mutations import ReportsMutations
from apps.reports.graphql.queries import ReportsQuery
from baseapp_auth.graphql.queries import UsersQuery
from graphene import relay


class Query(
    graphene.ObjectType,
    ClassroomQuery,
    CommentsQuery,
    UsersQuery,
    CitiesQuery,
    ReportsQuery,
):
    node = relay.node.NodeField(relay.Node)


class Mutation(graphene.ObjectType, CommentsMutations, ReactionsMutations, ReportsMutations):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
