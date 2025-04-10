from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import path

from . import views

url_shortening_prefix = getattr(settings, "URL_SHORTENING_PREFIX", None)
if not isinstance(url_shortening_prefix, str):
    raise ImproperlyConfigured("URL_SHORTENING_PREFIX must be a string")

urlpatterns = [
    path(
        f"{settings.URL_SHORTENING_PREFIX}/<str:short_code>",
        views.redirect_full_url,
        name="short_url_redirect_full_url",
    )
]
