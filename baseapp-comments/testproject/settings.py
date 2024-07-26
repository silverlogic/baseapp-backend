from baseapp_core.tests.settings import *  # noqa
from django.utils.translation import gettext_lazy as _

# Application definition
INSTALLED_APPS += [
    "graphene_django",
    "baseapp_profiles",
    "baseapp_blocks",
    "baseapp_notifications",
    "baseapp_reactions",
    "baseapp_comments",
    "baseapp_reports",
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
    "baseapp_auth.permissions.UsersPermissionsBackend",
    "baseapp_comments.permissions.CommentsPermissionsBackend",
    "baseapp_profiles.permissions.ProfilesPermissionsBackend",
]

BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = False

NOTIFICATIONS_NOTIFICATION_MODEL = "baseapp_notifications.Notification"
