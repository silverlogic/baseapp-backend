import os
from datetime import timedelta

from baseapp_core.tests.settings import *  # noqa

SOCIAL_AUTH_BEAT_SCHEDULES = {
    "clean-up-social-auth-cache": {
        "task": "baseapp_social_auth.cache.tasks.clean_up_social_auth_cache",
        "schedule": timedelta(hours=1),
        "options": {"expires": 60 * 30},
    },
}

SOCIAL_AUTH_PIPELINE = [
    # Get the information we can about the user and return it in a simple
    # format to create the user instance later. On some cases the details are
    # already part of the auth response from the provider, but sometimes this
    # could hit a provider API.
    "social_core.pipeline.social_auth.social_details",
    # Get the social uid from whichever service we're authing thru. The uid is
    # the unique identifier of the given user in the provider.
    "social_core.pipeline.social_auth.social_uid",
    # Verifies that the current auth process is valid within the current
    # project, this is where emails and domains whitelists are applied (if
    # defined).
    "social_core.pipeline.social_auth.auth_allowed",
    # Checks if the current social-account is already associated in the site.
    "social_core.pipeline.social_auth.social_user",
    "baseapp_social_auth.cache.pipeline.associate_by_email",
    "baseapp_social_auth.cache.pipeline.cache_access_token",
    # Make up a username for this person and ensure it isn't taken.  If it is taken,
    # fail.
    "apps.users.pipeline.get_username",
    # Create a user account if we haven't found one yet.
    "social_core.pipeline.user.create_user",
    # Create the record that associated the social account with this user.
    "social_core.pipeline.social_auth.associate_user",
    # Populate the extra_data field in the social record with the values
    # specified by settings (and the default ones like access_token, etc).
    "social_core.pipeline.social_auth.load_extra_data",
    # Update the user record with any changed info from the auth service.
    "social_core.pipeline.user.user_details",
    "apps.users.pipeline.set_avatar",
    "apps.users.pipeline.set_is_new",
    "apps.referrals.pipeline.link_user_to_referrer",
]
SOCIAL_AUTH_USER_FIELDS = ["username", "first_name", "last_name"]

# Facebook
SOCIAL_AUTH_FACEBOOK_SCOPE = ["public_profile", "email"]
SOCIAL_AUTH_FACEBOOK_KEY = os.environ.get("SOCIAL_AUTH_FACEBOOK_KEY")
SOCIAL_AUTH_FACEBOOK_SECRET = os.environ.get("SOCIAL_AUTH_FACEBOOK_SECRET")
SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {"fields": "id,email,first_name,last_name"}

# Twitter
SOCIAL_AUTH_TWITTER_KEY = os.environ.get("SOCIAL_AUTH_TWITTER_KEY")
SOCIAL_AUTH_TWITTER_SECRET = os.environ.get("SOCIAL_AUTH_TWITTER_SECRET")

# Social Auth LinkedIn
SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY = os.environ.get("SOCIAL_AUTH_LINKEDIN_KEY")
SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET = os.environ.get("SOCIAL_AUTH_LINKEDIN_SECRET")
SOCIAL_AUTH_LINKEDIN_OAUTH2_SCOPE = ["r_basicprofile", "r_emailaddress"]
SOCIAL_AUTH_LINKEDIN_OAUTH2_FIELD_SELECTORS = [
    "email-address",
    "picture-urls::(original)",
]

# Google
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.environ.get("SOCIAL_AUTH_GOOGLE_KEY")
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.environ.get("SOCIAL_AUTH_GOOGLE_SECRET")
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = ["email"]
SOCIAL_AUTH_GOOGLE_OAUTH2_AUTH_EXTRA_ARGUMENTS = {
    "access_type": "offline",
    "approval_prompt": "force",
}
