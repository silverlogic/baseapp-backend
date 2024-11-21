from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from .base.rest_framework.router import api_router as base_api_router
from .medias.rest_framework.router import api_router as medias_api_router

urlpatterns = [
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("api/v2/base/", base_api_router.urls),
    path("api/v2/medias/", medias_api_router.urls),
    # TODO: Find a way to disable the Wagtail pages. If we remove this line, the system won't
    # generate the url_path. This path will render the wagtail pages using jinja2. Without it set,
    # the system won't provide a final path for the pages and we need it to generate the headless
    # pages.
    path("", include(wagtail_urls)),
]
