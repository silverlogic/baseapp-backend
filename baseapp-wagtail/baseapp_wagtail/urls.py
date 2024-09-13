from django.urls import include, path

from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls

# from .api.router import api_router

urlpatterns = [
    path("cms/", include(wagtailadmin_urls)),
    # path("api/v2/", api_router.urls),
    path('documents/', include(wagtaildocs_urls)),
    path('pages/', include(wagtail_urls)),
]
