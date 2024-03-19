import graphene

from baseapp_reports.graphql.mutations import ReportsMutations
from testproject.testapp.graphql.queries import UsersQueries


class Query(
    graphene.ObjectType,
    UsersQueries,
):
    pass


class Mutation(
    graphene.ObjectType,
    ReportsMutations,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
