from baseapp_core.tests.settings import *  # noqa

from baseapp_wagtail.settings import *  # noqa
from baseapp_wagtail.settings import (
    WAGTAIL_INSTALLED_APPS,
    WAGTAIL_INSTALLED_INTERNAL_APPS,
    WAGTAIL_MIDDLEWARE,
)

ROOT_URLCONF = "testproject.urls"

APPS_DIR = BASE_DIR

# Needed to handle images and documents. Each project will have it's own way of handling media files.
# Must be absolute URLs for use in emails.
MEDIA_ROOT = "/media/"
MEDIA_URL = "/media/"
STATIC_ROOT = "/static/"
STATIC_URL = "/static/"

if "INSTALLED_APPS" not in globals():
    INSTALLED_APPS = []

if "MIDDLEWARE" not in globals():
    MIDDLEWARE = []

INSTALLED_APPS += [
    *WAGTAIL_INSTALLED_APPS,
    *WAGTAIL_INSTALLED_INTERNAL_APPS,
    # baseapp_wagtail
    "testproject.base",
]

MIDDLEWARE += WAGTAIL_MIDDLEWARE
