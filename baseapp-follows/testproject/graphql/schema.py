import graphene

from baseapp_follows.graphql.mutations import FollowsMutations
from testproject.testapp.graphql.queries import UsersQuery


class Query(
    graphene.ObjectType,
    UsersQuery,
):
    pass


class Mutation(
    graphene.ObjectType,
    FollowsMutations,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
