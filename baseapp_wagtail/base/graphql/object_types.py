import graphene
from django.apps import apps
from graphene import relay
from graphene_django import DjangoObjectType
from grapple.registry import registry

from baseapp_wagtail.base.graphql.interfaces import WagtailPageInterface
from baseapp_wagtail.base.models import DefaultPageModel

wagtail_url_path_object_type_interfaces = []

if apps.is_installed("baseapp_pages"):
    from baseapp_pages.graphql import PageInterface

    wagtail_url_path_object_type_interfaces.append(PageInterface)

if apps.is_installed("baseapp_comments"):
    from baseapp_comments.graphql.object_types import CommentsInterface

    wagtail_url_path_object_type_interfaces.append(CommentsInterface)


class WagtailPageObjectType(DjangoObjectType):
    """
    Object type for connecting Wagtail pages with other baseapp interfaces. Use this when Wagtail
    pages must be retrieved via different baseapp interfaces.
    If only the Wagtail page interface is needed, use the graphql_interfaces attribute in the
    Wagtail page models. Note: You may need to extend the interface and resolve the id field as
    shown in WagtailCommentsInterface.
    """

    id = graphene.ID(required=True)
    data = graphene.Field(WagtailPageInterface)

    class Meta:
        model = DefaultPageModel
        interfaces = (
            relay.Node,
            *wagtail_url_path_object_type_interfaces,
        )
        name = "WagtailPage"

    @classmethod
    def is_type_of(cls, root, info):
        if isinstance(root, DefaultPageModel):
            return True
        return super().is_type_of(root, info)

    def resolve_id(self, info):
        return self.id

    def resolve_data(self, info):
        return self

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        if apps.is_installed("baseapp_pages"):
            from baseapp_pages.graphql.object_types import MetadataObjectType

            # TODO: (BA-2635) Complete the metadata for Wagtail pages when implementing the story BA-2635.
            return MetadataObjectType(
                meta_title=instance.title,
                meta_description=None,
                meta_og_image=None,
                meta_og_type="article",
            )
        return None


BASEAPP_WAGTAIL_TYPES = [
    *registry.models.values(),
    WagtailPageObjectType,
]
