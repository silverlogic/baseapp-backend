from wagtail.api.v2.router import WagtailAPIRouter
from wagtail.images.api.v2.views import ImagesAPIViewSet

api_router = WagtailAPIRouter("baseappwagtailapi_medias")
api_router.register_endpoint("images", ImagesAPIViewSet)

# If you need to register new endpoints, you can just override the path("api/v2/medias/", medias_api_router.urls)
# in the urls.py of your project.
