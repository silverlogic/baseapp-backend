import graphene
from graphene.relay.node import NodeField as RelayNodeField
from graphene_django.debug import DjangoDebug

from baseapp_core.graphql import DeleteNode
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import plugin_registry
from testproject.users.graphql.queries import UsersQueries

queries = plugin_registry.get_all_graphql_queries()
mutations = plugin_registry.get_all_graphql_mutations()
subscriptions = plugin_registry.get_all_graphql_subscriptions()


class Query(
    graphene.ObjectType,
    UsersQueries,
    *queries,
):
    node = RelayNodeField(RelayNode)
    debug = graphene.Field(DjangoDebug, name="_debug")


class Mutation(
    graphene.ObjectType,
    *mutations,
):
    delete_node = DeleteNode.Field()


class Subscription(
    graphene.ObjectType,
    *subscriptions,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
