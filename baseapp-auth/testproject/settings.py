from collections import OrderedDict

from baseapp_core.settings.env import env
from baseapp_core.tests.settings import *  # noqa
from celery.schedules import crontab

APPS_DIR = BASE_DIR

# Application definition
INSTALLED_APPS += [
    "constance",
    "constance.backends.database",
    "channels",
    "avatar",
    "trench",
    "rest_framework_simplejwt",
    "baseapp_auth",
    "testproject.testapp",
]

ROOT_URLCONF = "testproject.urls"

CELERY_BEAT_SCHEDULE = {
    "notify_is_password_expired": {
        "task": "baseapp_auth.tasks.notify_users_is_password_expired",
        "schedule": crontab(hour=7, minute=7),
        "options": {"expires": 60 * 60 * 11},
    },
}

# Constance
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
CONSTANCE_CONFIG = OrderedDict(
    [
        (
            "USER_PASSWORD_EXPIRATION_INTERVAL",
            (
                365 * 2,
                "The time interval (in days) after which a user will need to reset their password.",
            ),
        ),
    ]
)

# Rest Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PAGINATION_CLASS": "baseapp_core.rest_framework.pagination.DefaultPageNumberPagination",
    "PAGE_SIZE": 30,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "ORDERING_PARAM": "order_by",
    "SEARCH_PARAM": "q",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# Auth
AUTH_USER_MODEL = "testapp.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]

# Sites
URL = env("URL", "", required=False)
FRONT_URL = env("FRONT_URL", "", required=False)
FRONT_CONFIRM_EMAIL_URL = FRONT_URL + "/confirm-email/{id}/{token}"
FRONT_FORGOT_PASSWORD_URL = FRONT_URL + "/forgot-password/{token}"
FRONT_CHANGE_EMAIL_CONFIRM_URL = FRONT_URL + "/change-email/{id}/{token}"
FRONT_CHANGE_EMAIL_VERIFY_URL = FRONT_URL + "/change-email-verify/{id}/{token}"

# IOS Deep Links
IOS_CONFIRM_EMAIL_DEEP_LINK = False
IOS_FORGOT_PASSWORD_DEEP_LINK = False
IOS_CHANGE_EMAIL_DEEP_LINK = False

# Android Deep Links
ANDROID_CONFIRM_EMAIL_DEEP_LINK = False
ANDROID_FORGOT_PASSWORD_DEEP_LINK = False
ANDROID_CHANGE_EMAIL_DEEP_LINK = False

# Phone Numbers
PHONENUMBER_DB_FORMAT = "E164"

# BRANCH.IO
BRANCHIO_KEY = env("BRANCHIO_KEY", "N/A")

TEMPLATES = [
    {
        "BACKEND": "django_jinja.backend.Jinja2",
        "DIRS": [str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "match_extension": ".j2",
            "constants": {"URL": URL, "FRONT_URL": FRONT_URL},
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
]

# Email
DEFAULT_FROM_EMAIL = "john@test.com"
DJMAIL_REAL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Must be absolute URLs for use in emails.
MEDIA_ROOT = str(BASE_DIR.parent / "media")
MEDIA_URL = "{url}/media/".format(url=URL)
STATIC_ROOT = str(BASE_DIR.parent / "static")
STATIC_URL = "{url}/static/".format(url=URL)

# JWT Authentication
SIMPLE_JWT = {
    # It will work instead of the default serializer(TokenObtainPairSerializer).
    "TOKEN_OBTAIN_SERIALIZER": "testproject.testapp.rest_framework.jwt.serializers.MyTokenObtainPairSerializer",
    # ...
}
JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"

# Baseapp Auth
BASEAPP_AUTH_USER_FACTORY = "testproject.testapp.tests.factories.UserFactory"
