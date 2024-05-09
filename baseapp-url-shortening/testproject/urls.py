from django.contrib import admin
from django.urls import include, re_path

__all__ = [
    "urlpatterns",
]

v1_urlpatterns = [
    re_path(r"", include("baseapp_url_shortening.urls")),
]

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(r"v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
]
