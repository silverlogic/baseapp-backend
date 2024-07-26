import graphene

from baseapp_blocks.graphql.mutations import BlocksMutations
from testproject.testapp.graphql.queries import UsersQueries


class Query(
    graphene.ObjectType,
    UsersQueries,
):
    pass


class Mutation(
    graphene.ObjectType,
    BlocksMutations,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
