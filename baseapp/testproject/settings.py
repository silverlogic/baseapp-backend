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
    "baseapp.activity_log",
    "testproject.testapp",
    "testproject.comments",
    "testproject.profiles",
]

MIDDLEWARE.remove("baseapp_core.middleware.HistoryMiddleware")
MIDDLEWARE += [
    "baseapp_profiles.middleware.CurrentProfileMiddleware",
    "baseapp_core.middleware.HistoryMiddleware",
]

GRAPHENE["MIDDLEWARE"] = (
    "baseapp_profiles.graphql.middleware.CurrentProfileMiddleware",
) + GRAPHENE["MIDDLEWARE"]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "testapp.User"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]

CELERY_BROKER_URL = "memory:///"
CELERY_RESULT_BACKEND = "cache+memory:///"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_profiles.permissions.ProfilesPermissionsBackend",
    "baseapp_comments.permissions.CommentsPermissionsBackend",
    "baseapp.activity_log.permissions.ActivityLogPermissionsBackend",
]

BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = False

# NOTIFICATIONS_NOTIFICATION_MODEL = "baseapp_notifications.Notification"

# Comments
BASEAPP_COMMENTS_COMMENT_MODEL = "comments.Comment"

# Profiles
BASEAPP_PROFILES_PROFILE_MODEL = "profiles.Profile"
