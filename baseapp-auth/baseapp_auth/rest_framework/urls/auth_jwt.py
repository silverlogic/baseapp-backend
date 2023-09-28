from django.urls import re_path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    # JWT login
    re_path(r"login", TokenObtainPairView.as_view(), name="jwt"),
    # JWT token refresh
    re_path(r"refresh", TokenRefreshView.as_view(), name="jwt-token-refresh"),
]
