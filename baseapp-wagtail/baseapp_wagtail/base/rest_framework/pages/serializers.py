from rest_framework.fields import Field
from wagtail.api.v2.serializers import PageSerializer as WagtailPageSerializer
from wagtail.api.v2.serializers import get_serializer_class


class PageFeaturedImage(Field):
    def get_attribute(self, instance):
        obj = instance.specific
        if hasattr(obj, "featured_image"):
            return obj.featured_image
        return None

    def to_representation(self, value):
        if not value:
            return None
        item = list(value).pop()
        return item.block.get_api_representation(item.value, context=self.context)


class OptionalMetaField(Field):
    """
    Some fields set in the page model might not be present in other page models that use the same
    serializer. This class is used to handle the absence of the field in the model.
    """

    def get_attribute(self, instance):
        obj = instance.specific
        if hasattr(obj, self.field_name):
            return getattr(obj, self.field_name)
        return None

    def to_representation(self, value):
        if not value:
            return None
        return value


class PageUrlPath(Field):
    def get_attribute(self, instance):
        return instance

    def to_representation(self, page):
        try:
            url_parts = page.get_url_parts()
            _, _, page_path = url_parts
            return page_path
        except (AttributeError, ValueError):
            return None


class PageAncestors(Field):
    def get_attribute(self, instance):
        return instance

    def to_representation(self, page):
        """
        Method based on get_breadcrumbs_items_for_page from Wagtail.
        """
        include_self = False
        pages = (
            page.get_ancestors(inclusive=include_self)
            .descendant_of(page.get_first_root_node(), inclusive=False)
            .filter(live=True)
            .specific(defer=True)
        )

        ancestors = []
        for ancestor in pages:
            serializer_class = get_serializer_class(
                ancestor.__class__,
                ["id", "type", "title", "url_path", "locale"],
                meta_fields=["*"],
                base=CustomPageSerializer,
            )
            serializer = serializer_class(context=self.context)
            ancestors.append(serializer.to_representation(ancestor))
        return ancestors


class CustomPageSerializer(WagtailPageSerializer):
    featured_image = PageFeaturedImage(read_only=True)
    url_path = PageUrlPath(read_only=True)
    ancestors = PageAncestors(read_only=True)
