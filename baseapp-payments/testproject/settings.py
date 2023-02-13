import os
import sys

from baseapp_core.settings.env import env
from baseapp_core.tests.settings import *  # noqa

# import from source code dir
here = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, os.pardir))

SITE_ID = 300

DEBUG = True

ROOT_URLCONF = "testproject.urls"
SECRET_KEY = "very-secret"

AUTOCOMMIT = True

DATABASES = {
    "default": {
        "NAME": "test.db",
        "ENGINE": "django.db.backends.sqlite3",
        "USER": "",
        "PASSWORD": "",
        "PORT": "",
    },
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
]

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    # Third party
    "djstripe",
    "constance",
    "constance.backends.database",
    "baseapp_payments",
]

USE_TZ = True
TIME_ZONE = "UTC"
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

STATIC_ROOT = "./static/"
STATIC_URL = "/static/"

DJANGO_SUPERUSER_PASSWORD = "1234"
DJANGO_SUPERUSER_EMAIL = "example@tsl.io"
DJANGO_SUPERUSER_USERNAME = "admin"

STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY", "N/A")
STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY", "N/A")
STRIPE_LIVE_MODE = env("STRIPE_LIVE_MODE", "N/A")  # Change to True in production
DJSTRIPE_WEBHOOK_SECRET = env("DJSTRIPE_WEBHOOK_SECRET", "N/A")
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"
