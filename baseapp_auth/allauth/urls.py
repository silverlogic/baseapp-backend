"""
URL patterns for django-allauth admin redirects and headless API.

These URLs redirect Django admin authentication URLs to django-allauth views,
providing a seamless integration between Django admin and allauth.
Also includes headless API endpoints for API-based authentication flows.
"""

from django.urls import include, path, re_path
from django.views.generic.base import RedirectView

urlpatterns = [
    re_path(
        r"^admin/login/",
        RedirectView.as_view(pattern_name="account_login", query_string=True, permanent=False),
    ),
    re_path(
        r"^admin/logout/",
        RedirectView.as_view(pattern_name="account_logout", query_string=True, permanent=True),
    ),
    re_path(
        r"^admin/password_change/",
        RedirectView.as_view(
            pattern_name="account_change_password", query_string=True, permanent=True
        ),
    ),
    re_path(
        r"^admin/password_change/done/",
        RedirectView.as_view(pattern_name="admin:index", query_string=True, permanent=True),
    ),
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
]
