from baseapp_wagtail.base.rest_framework.pages.serializers import PageUrlPath
from wagtail.api.v2.serializers import PageSerializer as WagtailPageSerializer


class SitemapPageSerializer(WagtailPageSerializer):
    url_path = PageUrlPath(read_only=True)
