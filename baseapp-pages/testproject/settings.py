from django.utils.translation import gettext_lazy as _

from baseapp_core.tests.settings import *  # noqa

# Application definition
INSTALLED_APPS += [
    "graphene_django",
    "baseapp_pages",
    "django_quill",
    "baseapp_reactions",
    "baseapp_comments",
    "baseapp_reports",
    "baseapp_profiles",
    "baseapp_blocks",
    "baseapp_auth",
    "baseapp_follows",
    "testproject.testapp",
]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "testapp.User"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_pages.permissions.PagesPermissionsBackend",
    "baseapp_comments.permissions.CommentsPermissionsBackend",
]
