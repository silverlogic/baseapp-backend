from wagtail.api.v2.serializers import PageSerializer as WagtailPageSerializer

from baseapp_wagtail.api.pages.serializers import PageUrlPath


class SitemapPageSerializer(WagtailPageSerializer):
    url_path = PageUrlPath(read_only=True)
