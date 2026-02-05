from celery.schedules import crontab
from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import plugin_registry
from baseapp_core.tests.settings import *  # noqa
from baseapp_wagtail.settings import *  # noqa
from baseapp_wagtail.settings import (
    WAGTAIL_INSTALLED_APPS,
    WAGTAIL_INSTALLED_INTERNAL_APPS,
    WAGTAIL_MIDDLEWARE,
)

plugin_settings = plugin_registry.get_all_django_settings()
for key, value in plugin_settings.items():
    if key not in globals():
        globals()[key] = value

# Application definition
INSTALLED_APPS += [
    "channels",
    "graphene_django",
    "notifications",
    "push_notifications",
    "django_quill",
    "social_django",
    "rest_social_auth",
    "trench",
    "rest_framework_simplejwt",
    "baseapp_profiles",
    "baseapp_reactions",
    "baseapp_reports",
    "baseapp_pages",
    "baseapp_comments",
    "baseapp_auth",
    "baseapp_referrals",
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
    "baseapp_social_auth",
    "baseapp_social_auth.cache",
    "testproject.users",
    "baseapp.content_feed",
    "baseapp_pdf",
    "baseapp_api_key",
    *WAGTAIL_INSTALLED_APPS,
    *WAGTAIL_INSTALLED_INTERNAL_APPS,
    *plugin_registry.get_all_installed_apps(),
    "testproject.testapp",
    "testproject.comments",
    "testproject.profiles",
    "testproject.reactions",
    "testproject.content_feed",
    "testproject.follows",
    "testproject.blocks",
    "testproject.base",
    "testproject.e2e",
    "testproject.ratings",
    "testproject.reports",
    "testproject.pages",
    "testproject.organizations",
    "testproject.chats",
    "baseapp_wagtail.tests",
]

MIDDLEWARE.remove("baseapp_core.middleware.HistoryMiddleware")
MIDDLEWARE += [
    "baseapp_profiles.middleware.CurrentProfileMiddleware",
    "baseapp_core.middleware.HistoryMiddleware",
    *WAGTAIL_MIDDLEWARE,
    *plugin_registry.get_all_middleware(),
]

GRAPHENE["MIDDLEWARE"] = (
    "baseapp_profiles.graphql.middleware.CurrentProfileMiddleware",
    *plugin_registry.get_all_graphql_middleware(),
) + GRAPHENE["MIDDLEWARE"]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "users.User"

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
CELERY_BEAT_SCHEDULE = {
    "notify_is_password_expired": {
        "task": "baseapp_auth.tasks.notify_users_is_password_expired",
        "schedule": crontab(hour=7, minute=7),
        "options": {"expires": 60 * 60 * 11},
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
    *plugin_registry.get_all_auth_backends(),
]

ADMIN_TIME_ZONE = "UTC"

# URL Shortening
URL_SHORTENING_PREFIX = "c"

# Wagtail
WAGTAIL_SITE_NAME = "Test Project"

# Constance
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
CONSTANCE_CONFIG = OrderedDict(
    [
        (
            "USER_PASSWORD_EXPIRATION_INTERVAL",
            (
                365 * 2,
                "The time interval (in days) after which a user will need to reset their password.",
            ),
        ),
        (
            "BLOCKLISTED_WORDS",
            ("", "Comma-separated list of blocked words for user generated content."),
        ),
        (
            "EMAIL_VERIFICATION_REQUIRED",
            (False, "Require email verification for new users."),
        ),
        (
            "STRIPE_CUSTOMER_ENTITY_MODEL",
            ("profiles.Profile", "The model to use for the Stripe customer entity."),
        ),
        (
            "ENABLE_PUBLIC_ID_LOGIC",
            (True, "Enable public ID logic."),
        ),
        (
            "ANONYMIZE_TASK_DELAY_DAYS",
            (19, "Delay in days before running anonymize user task"),
        ),
        (
            "SEND_USER_ANONYMIZE_EMAIL_TO_SUPERUSERS",
            (False, "Whether to send anonymize/delete user notification emails to superusers"),
        ),
    ]
    + plugin_registry.get_all_constance_config(),
)

# Stripe
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")

# Profiles
BASEAPP_PROFILES_PROFILE_MODEL = "profiles.Profile"
BASEAPP_PROFILES_PROFILEUSERROLE_MODEL = "profiles.ProfileUserRole"

# Reactions
BASEAPP_REACTIONS_REACTION_MODEL = "reactions.Reaction"

# Comments
BASEAPP_COMMENTS_COMMENT_MODEL = "comments.Comment"
BASEAPP_COMMENTS_COMMENTSTATS_MODEL = "comments.CommentStats"

# Content Feed
BASEAPP_CONTENT_FEED_CONTENTPOST_MODEL = "content_feed.ContentPost"
BASEAPP_CONTENT_FEED_CONTENTPOSTIMAGE_MODEL = "content_feed.ContentPostImage"

# Follows
BASEAPP_FOLLOWS_FOLLOW_MODEL = "follows.Follow"

# Blocks
BASEAPP_BLOCKS_BLOCK_MODEL = "blocks.Block"

# Ratings
BASEAPP_RATINGS_RATE_MODEL = "ratings.Rate"

# Reports
BASEAPP_REPORTS_REPORT_MODEL = "reports.Report"
BASEAPP_REPORTS_REPORTTYPE_MODEL = "reports.ReportType"

# Pages
BASEAPP_PAGES_PAGE_MODEL = "pages.Page"

# Organizations
BASEAPP_ORGANIZATIONS_ORGANIZATION_MODEL = "organizations.Organization"

# Chats
BASEAPP_CHATS_CHATROOM_MODEL = "chats.ChatRoom"
BASEAPP_CHATS_CHATROOMPARTICIPANT_MODEL = "chats.ChatRoomParticipant"
BASEAPP_CHATS_UNREADMESSAGECOUNT_MODEL = "chats.UnreadMessageCount"
BASEAPP_CHATS_MESSAGE_MODEL = "chats.Message"
BASEAPP_CHATS_MESSAGESTATUS_MODEL = "chats.MessageStatus"

# Notifications
NOTIFICATIONS_NOTIFICATION_MODEL = "baseapp_notifications.Notification"
BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = False
BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS = False

# API Key
BA_API_KEY_REQUEST_HEADER = env("BA_API_KEY_REQUEST_HEADER", default="HTTP_API_KEY")
BA_API_KEY_ENCRYPTION_KEY = env("BA_API_KEY_ENCRYPTION_KEY", default=None)

# Graphene query optimizer
GRAPHQL_QUERY_OPTIMIZER = {
    "ALLOW_CONNECTION_AS_DEFAULT_NESTED_TO_MANY_FIELD": True,
}

# End-to-end tests
E2E = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "testproject.e2e.scripts",
}

# Social auth
SOCIAL_AUTH_PIPELINE_MODULE = "baseapp_social_auth.tests.pipeline"
SOCIAL_AUTH_FACEBOOK_KEY = "1234"
SOCIAL_AUTH_FACEBOOK_SECRET = "abcd"
SOCIAL_AUTH_TWITTER_KEY = "1234"
SOCIAL_AUTH_TWITTER_SECRET = "1234"
SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY = "1234"
SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET = "1234"
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = "1234"
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = "1234"
SOCIAL_AUTH_PIPELINE = [
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "baseapp_social_auth.cache.pipeline.cache_access_token",
    "baseapp_social_auth.tests.pipeline.get_username",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "baseapp_social_auth.tests.pipeline.set_avatar",
    "baseapp_social_auth.tests.pipeline.set_is_new",
    "baseapp_social_auth.tests.pipeline.link_user_to_referrer",
]
from baseapp_social_auth.settings import (  # noqa
    SOCIAL_AUTH_BEAT_SCHEDULES,
    SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS,
    SOCIAL_AUTH_FACEBOOK_SCOPE,
    SOCIAL_AUTH_GOOGLE_OAUTH2_AUTH_EXTRA_ARGUMENTS,
    SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE,
    SOCIAL_AUTH_LINKEDIN_OAUTH2_FIELD_SELECTORS,
    SOCIAL_AUTH_LINKEDIN_OAUTH2_SCOPE,
    SOCIAL_AUTH_USER_FIELDS,
)

if SOCIAL_AUTH_FACEBOOK_KEY and SOCIAL_AUTH_FACEBOOK_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.facebook.FacebookOAuth2")
if SOCIAL_AUTH_TWITTER_KEY and SOCIAL_AUTH_TWITTER_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.twitter.TwitterOAuth")
if SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY and SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.linkedin.LinkedinOAuth2")
if SOCIAL_AUTH_GOOGLE_OAUTH2_KEY and SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.google.GoogleOAuth2")

# JWT Authentication
SIMPLE_JWT = {
    # It will work instead of the default serializer(TokenObtainPairSerializer).
    "TOKEN_OBTAIN_SERIALIZER": "testproject.users.rest_framework.jwt.serializers.MyTokenObtainPairSerializer",
    # ...
}
JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"

# Sites
FRONT_CONFIRM_EMAIL_URL = FRONT_URL + "/confirm-email/{id}/{token}"
FRONT_FORGOT_PASSWORD_URL = FRONT_URL + "/forgot-password/{token}"
FRONT_CHANGE_EMAIL_CONFIRM_URL = FRONT_URL + "/change-email/{id}/{token}"
FRONT_CHANGE_EMAIL_VERIFY_URL = FRONT_URL + "/change-email-verify/{id}/{token}"
FRONT_CHANGE_EXPIRED_PASSWORD_URL = FRONT_URL + "/change-expired-password/{token}"

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

# AUTOFIELD
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
