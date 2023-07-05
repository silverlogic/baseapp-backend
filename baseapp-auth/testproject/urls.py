from django.conf.urls import include, re_path

from baseapp_auth.rest_framework.router import router as v1_router

urlpatterns = [
    re_path(r"v1/auth/", include("trench.urls")),
    re_path(r"v1/", include((v1_router.urls, "v1"), namespace="v1")),
]
