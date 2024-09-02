from baseapp_core.tests.settings import *  # noqa
from django.utils.translation import gettext_lazy as _

# Application definition
INSTALLED_APPS += [
    "graphene_django",
    "baseapp_reports",
    "baseapp_auth",
    "baseapp_profiles",
    "baseapp_reactions",
    "baseapp_comments",
    "baseapp_follows",
    "baseapp_blocks",
    "testproject.testapp",
]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "testapp.User"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_auth.permissions.UsersPermissionsBackend",
    "baseapp_reports.permissions.ReportsPermissionsBackend",
]

BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = False

NOTIFICATIONS_NOTIFICATION_MODEL = "baseapp_notifications.Notification"
