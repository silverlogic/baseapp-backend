from baseapp_core.tests.settings import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS += [
    # baseapp_social_auth
    "avatar",
    "testproject.testapp",
    "social_django",
    "rest_social_auth",
    "baseapp_social_auth",
    "baseapp_referrals",
    "baseapp_social_auth.cache",
]

ROOT_URLCONF = "testproject.urls"

AUTH_USER_MODEL = "testapp.User"

# Social auth
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
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
