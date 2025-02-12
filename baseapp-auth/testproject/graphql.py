import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_devices.graphql.queries import UserDeviceQueries
from graphene import relay


class Query(graphene.ObjectType, UsersQueries, UserDeviceQueries):
    node = relay.node.NodeField(relay.Node)


schema = graphene.Schema(query=Query)
