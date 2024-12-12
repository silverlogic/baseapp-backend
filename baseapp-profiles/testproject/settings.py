from baseapp_core.tests.settings import *  # noqa
from django.utils.translation import gettext_lazy as _

# Application definition
INSTALLED_APPS += [
    "graphene_django",
    "baseapp_profiles",
    "baseapp_reactions",
    "baseapp_reports",
    "baseapp_pages",
    "baseapp_comments",
    "baseapp_auth",
    "baseapp_follows",
    "baseapp_blocks",
    "testproject.testapp",
]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "testapp.User"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]

BROKER_URL = "memory:///"
CELERY_BROKER_URL = "memory:///"
CELERY_RESULT_BACKEND = "cache+memory:///"
BROKER_BACKEND = "memory"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_profiles.permissions.ProfilesPermissionsBackend",
    "baseapp_comments.permissions.CommentsPermissionsBackend",
]
