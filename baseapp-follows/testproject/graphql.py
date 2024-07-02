import graphene
from baseapp_profiles.graphql.queries import ProfilesQueries

from baseapp_follows.graphql.mutations import FollowsMutations
from testproject.testapp.graphql.queries import UsersQueries


class Query(
    graphene.ObjectType,
    UsersQueries,
    ProfilesQueries,
):
    pass


class Mutation(
    graphene.ObjectType,
    FollowsMutations,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
