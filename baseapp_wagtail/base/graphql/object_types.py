import graphene
from graphene import relay

from baseapp_pages.graphql import PageInterface
from baseapp_wagtail.base.graphql.interfaces import WagtailPageInterface


class WagtailURLPathObjectType(graphene.ObjectType):
    data = graphene.Field(WagtailPageInterface)

    class Meta:
        interfaces = (
            relay.Node,
            PageInterface,
        )
        name = "WagtailPage"

    @classmethod
    def resolve_type(cls, instance, info):
        return cls

    def resolve_data(self, info):
        return self

    # TODO: (BA-2636) Solve the metadata interface.
