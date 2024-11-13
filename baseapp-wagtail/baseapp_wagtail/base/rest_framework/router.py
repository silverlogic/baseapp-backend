from wagtail.api.v2.router import WagtailAPIRouter

from .page_preview.views import PagePreviewAPIViewSet
from .pages.views import CustomPagesAPIEndpoint
from .redirects.views import CustomRedirectsAPIViewSet
from .sitemap.views import SitemapAPIViewSet

api_router = WagtailAPIRouter("baseappwagtailapi_base")

# Add the wagtail and custom endpoints using the "register_endpoint" method.
# The first parameter is the name of the endpoint (eg. pages, images). This is used in the URL of
# the endpoint.
# The second parameter is the endpoint class that handles the requests
api_router.register_endpoint("pages", CustomPagesAPIEndpoint)
api_router.register_endpoint("page_preview", PagePreviewAPIViewSet)
api_router.register_endpoint("sitemap/pages", SitemapAPIViewSet)
api_router.register_endpoint("redirects", CustomRedirectsAPIViewSet)

# If you need to register new endpoints, you can just override the path("api/v2/base/", base_api_router.urls)
# in the urls.py of your project.
