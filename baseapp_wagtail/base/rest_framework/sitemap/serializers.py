from rest_framework.fields import Field
from wagtail.api.v2.serializers import PageSerializer as WagtailPageSerializer


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


class SitemapPageSerializer(WagtailPageSerializer):
    url_path = PageUrlPath(read_only=True)
