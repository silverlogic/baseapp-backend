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

    def resolve_data(self, info):
        return self

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        if apps.is_installed("baseapp_pages"):
            from django.contrib.contenttypes.models import ContentType
            from django.utils.translation import get_language

            from baseapp_pages.graphql.object_types import MetadataObjectType
            from baseapp_pages.models import Metadata

            target_content_type = ContentType.objects.get_for_model(instance)
            metadata = Metadata.objects.filter(
                target_content_type=target_content_type,
                target_object_id=instance.id,
                language=get_language(),
            ).first()

            if metadata:
                return metadata

            # Fallback to Wagtail fields if no Metadata object exists
            return MetadataObjectType(
                meta_title=instance.title,
                meta_description=instance.search_description,
                meta_og_type="article",
            )
        return None


BASEAPP_WAGTAIL_TYPES = [
    *registry.models.values(),
    WagtailPageObjectType,
]
