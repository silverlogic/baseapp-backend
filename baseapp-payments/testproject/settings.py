from baseapp_core.settings.env import env
from baseapp_core.tests.settings import *  # noqa

SITE_ID = 300

ROOT_URLCONF = "testproject.urls"

AUTOCOMMIT = True

INSTALLED_APPS += [
    # Django
    "django.contrib.sites",
    # Third party
    "djstripe",
    "constance",
    "baseapp_payments",
]

STATIC_ROOT = "./static/"

DJANGO_SUPERUSER_PASSWORD = "1234"
DJANGO_SUPERUSER_EMAIL = "example@tsl.io"
DJANGO_SUPERUSER_USERNAME = "admin"

STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY", "sk_live_N/A")
STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY", "N/A")
STRIPE_LIVE_MODE = env("STRIPE_LIVE_MODE", "N/A")  # Change to True in production
DJSTRIPE_WEBHOOK_SECRET = env("DJSTRIPE_WEBHOOK_SECRET", "N/A")
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"
