from django.utils.translation import gettext_lazy as _

from baseapp_core.tests.settings import *  # noqa
from baseapp_wagtail.settings import *  # noqa
from baseapp_wagtail.settings import (
    WAGTAIL_INSTALLED_APPS,
    WAGTAIL_INSTALLED_INTERNAL_APPS,
    WAGTAIL_MIDDLEWARE,
)

# Application definition
INSTALLED_APPS += [
    "graphene_django",
    "notifications",
    "push_notifications",
    "django_quill",
    "baseapp_profiles",
    "baseapp_reactions",
    "baseapp_reports",
    "baseapp_pages",
    "baseapp_comments",
    "baseapp_auth",
    "baseapp_follows",
    "baseapp_blocks",
    "baseapp.activity_log",
    "baseapp_notifications",
    "baseapp_ratings",
    "baseapp_payments",
    "baseapp_message_templates",
    "baseapp_url_shortening",
    "baseapp_organizations",
    "baseapp_chats",
    "baseapp_e2e",
    "testproject.testapp",
    "testproject.comments",
    "testproject.profiles",
    "testproject.base",
    *WAGTAIL_INSTALLED_INTERNAL_APPS,
    *WAGTAIL_INSTALLED_APPS,
    "baseapp_wagtail.tests",
]

MIDDLEWARE.remove("baseapp_core.middleware.HistoryMiddleware")
MIDDLEWARE += [
    "baseapp_profiles.middleware.CurrentProfileMiddleware",
    "baseapp_core.middleware.HistoryMiddleware",
    *WAGTAIL_MIDDLEWARE,
]

GRAPHENE["MIDDLEWARE"] = (
    "baseapp_profiles.graphql.middleware.CurrentProfileMiddleware",
) + GRAPHENE["MIDDLEWARE"]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "testapp.User"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]

# Celery
CELERY_BROKER_URL = "memory:///"
CELERY_RESULT_BACKEND = "cache+memory:///"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ROUTES = {
    "baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare": {
        "exchange": "default",
        "routing_key": "default",
    },
    "baseapp_cloudflare_stream_field.tasks.generate_download_url": {
        "exchange": "default",
        "routing_key": "default",
    },
}

# Cloudflare
CLOUDFLARE_ACCOUNT_ID = "023e105f4ecef8ad9ca31a8372d0c353"
CLOUDFLARE_API_TOKEN = "1234567890abcdef1234567890abcdef"
CLOUDFLARE_AUTH_EMAIL = ""
CLOUDFLARE_VIDEO_AUTOMATIC_TRIM = True
CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS = 10

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_auth.permissions.UsersPermissionsBackend",
    "baseapp_profiles.permissions.ProfilesPermissionsBackend",
    "baseapp_comments.permissions.CommentsPermissionsBackend",
    "baseapp.activity_log.permissions.ActivityLogPermissionsBackend",
    "baseapp_reactions.permissions.ReactionsPermissionsBackend",
    "baseapp_reports.permissions.ReportsPermissionsBackend",
    "baseapp_ratings.permissions.RatingsPermissionsBackend",
    "baseapp_follows.permissions.FollowsPermissionsBackend",
    "baseapp_blocks.permissions.BlocksPermissionsBackend",
    "baseapp_pages.permissions.PagesPermissionsBackend",
    "baseapp_organizations.permissions.OrganizationsPermissionsBackend",
    "baseapp_chats.permissions.ChatsPermissionsBackend",
]

ADMIN_TIME_ZONE = "UTC"

# URL Shortening
URL_SHORTENING_PREFIX = "c"

# Wagtail
WAGTAIL_SITE_NAME = "Test Project"

# Constance
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"

# Stripe
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")

# Comments
BASEAPP_COMMENTS_COMMENT_MODEL = "comments.Comment"

# Profiles
BASEAPP_PROFILES_PROFILE_MODEL = "profiles.Profile"

# Notifications
NOTIFICATIONS_NOTIFICATION_MODEL = "baseapp_notifications.Notification"
BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = False
BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS = False

# Graphene query optimizer
GRAPHQL_QUERY_OPTIMIZER = {
    "ALLOW_CONNECTION_AS_DEFAULT_NESTED_TO_MANY_FIELD": True,
}

# End-to-end tests
E2E = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "testproject.e2e.scripts",
}
