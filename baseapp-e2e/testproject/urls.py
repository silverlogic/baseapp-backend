from baseapp_core.rest_framework.routers import DefaultRouter
from baseapp_e2e.rest_framework.views import E2EViewSet
from django.contrib import admin
from django.urls import include, path, re_path

router = DefaultRouter(trailing_slash=False)

router.register(r"e2e", E2EViewSet, basename="e2e")

urlpatterns = [
    path("admin/", admin.site.urls),
    re_path(r"", include(router.urls)),
]
