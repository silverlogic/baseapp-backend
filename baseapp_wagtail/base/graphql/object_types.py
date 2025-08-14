import graphene
from django.apps import apps
from graphene import relay
from grapple.registry import registry

from baseapp_wagtail.base.graphql.interfaces import WagtailPageInterface

wagtail_url_path_object_type_interfaces = []
if apps.is_installed("baseapp_pages"):
    from baseapp_pages.graphql import PageInterface

    wagtail_url_path_object_type_interfaces.append(PageInterface)


class WagtailURLPathObjectType(graphene.ObjectType):
    data = graphene.Field(WagtailPageInterface)

    class Meta:
        interfaces = (
            relay.Node,
            *wagtail_url_path_object_type_interfaces,
        )
        name = "WagtailPage"

    @classmethod
    def resolve_type(cls, instance, info):
        return cls

    def resolve_data(self, info):
        return self

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        if apps.is_installed("baseapp_pages"):
            from baseapp_pages.graphql.object_types import AbstractMetadataObjectType

            class WagtailMetadata(AbstractMetadataObjectType):
                # TODO: (BA-2635) Complete the metadata for Wagtail pages when implementing the story BA-2635.
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

            return WagtailMetadata(instance, info)
        return None


BASEAPP_WAGTAIL_TYPES = [
    *registry.models.values(),
    WagtailURLPathObjectType,
]
