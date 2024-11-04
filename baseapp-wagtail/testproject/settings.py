from pathlib import Path

from baseapp_core.tests.settings import *  # noqa

from baseapp_wagtail.settings import *  # noqa
from baseapp_wagtail.settings import (
    WAGTAIL_INSTALLED_APPS,
    WAGTAIL_INSTALLED_INTERNAL_APPS,
    WAGTAIL_MIDDLEWARE,
)

ROOT_URLCONF = "testproject.urls"

BASE_DIR = Path(__file__).resolve().parent.parent

APPS_DIR = BASE_DIR

# Needed to handle images and documents. Each project will have it's own way of handling media files.
# Must be absolute URLs for use in emails.
MEDIA_ROOT = str(BASE_DIR.parent / "media")
MEDIA_URL = "/media/"
STATIC_ROOT = str(BASE_DIR.parent / "static")
STATIC_URL = "/static/"

if "INSTALLED_APPS" not in globals():
    INSTALLED_APPS = []

if "MIDDLEWARE" not in globals():
    MIDDLEWARE = []

INSTALLED_APPS += [
    # baseapp_wagtail
    "testproject.base",
    *WAGTAIL_INSTALLED_INTERNAL_APPS,
    *WAGTAIL_INSTALLED_APPS,
]

MIDDLEWARE += WAGTAIL_MIDDLEWARE

WAGTAIL_SITE_NAME = "Test Project"
