from django.contrib import admin
from django.urls import include, re_path

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(r"", include("baseapp_url_shortening.urls")),
]
