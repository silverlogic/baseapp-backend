import graphene
from graphene import relay

from baseapp_pages.graphql import PageInterface
from baseapp_pages.graphql.object_types import AbstractMetadataObjectType
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

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        # TODO: (BA-2636) Review metadata for Wagtail pages.
        return WagtailMetadata(instance, info)


class WagtailMetadata(AbstractMetadataObjectType):
    @property
    def meta_title(self):
        return self.instance.title

    @property
    def meta_description(self):
        return None

    @property
    def meta_og_type(self):
        return "article"

    @property
    def meta_og_image(self):
        return None
