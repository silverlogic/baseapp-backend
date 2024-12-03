import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from baseapp_ratings.graphql.mutations import RatingsMutations
from baseapp_ratings.graphql.queries import RatingsQueries
from graphene import relay


class Query(graphene.ObjectType, RatingsQueries, UsersQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    RatingsMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
