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


# Subscriptions might be empty, therefore we should only attach the Subscription root type if
# there are subscription fields. Graphene rejects a Mutation/Subscription type with zero fields
# ("Type X must define one or more fields").
schema_kwargs = {"query": Query, "mutation": Mutation}
if subscriptions:
    schema_kwargs["subscription"] = Subscription

schema = graphene.Schema(**schema_kwargs)
