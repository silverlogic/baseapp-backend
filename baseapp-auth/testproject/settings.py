from baseapp_core.settings.env import env
from baseapp_core.tests.settings import *  # noqa
from celery.schedules import crontab

APPS_DIR = BASE_DIR

# Application definition
INSTALLED_APPS += [
    "channels",
    "avatar",
    "allauth",
    "allauth.headless",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.usersessions",
    "allauth.mfa",
    "rest_framework_simplejwt",
    "baseapp_auth",
    "baseapp_profiles",
    "baseapp_reactions",
    "baseapp_comments",
    "baseapp_follows",
    "baseapp_blocks",
    "baseapp_reports",
    "testproject.testapp",
    "graphene_django",
]

MIDDLEWARE = [
    *MIDDLEWARE,
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "testproject.urls"

CELERY_BEAT_SCHEDULE = {
    "notify_is_password_expired": {
        "task": "baseapp_auth.tasks.notify_users_is_password_expired",
        "schedule": crontab(hour=7, minute=7),
        "options": {"expires": 60 * 60 * 11},
    },
}

# Auth
AUTH_USER_MODEL = "testapp.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_auth.permissions.UsersPermissionsBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]

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

# JWT Authentication
SIMPLE_JWT = {
    # It will work instead of the default serializer(TokenObtainPairSerializer).
    "TOKEN_OBTAIN_SERIALIZER": "testproject.testapp.rest_framework.jwt.serializers.MyTokenObtainPairSerializer",
    # ...
}
JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"

# Baseapp Auth
BASEAPP_AUTH_USER_FACTORY = "testproject.testapp.tests.factories.UserFactory"

# AllAuth MFA
MFA_ADAPTER = "baseapp_auth.extensions.allauth.account.adapter.MFAAdapter"
MFA_FORMS = {
    "authenticate": "allauth.mfa.base.forms.AuthenticateForm",
    "reauthenticate": "allauth.mfa.base.forms.AuthenticateForm",
    "activate_totp": "allauth.mfa.totp.forms.ActivateTOTPForm",
    "deactivate_totp": "allauth.mfa.totp.forms.DeactivateTOTPForm",
    "generate_recovery_codes": "allauth.mfa.recovery_codes.forms.GenerateRecoveryCodesForm",
}
MFA_RECOVERY_CODE_COUNT = 10
MFA_TOTP_DIGITS = 6
MFA_TOTP_ISSUER = "BaseApp"
MFA_SUPPORTED_TYPES = [
    # TODO: MFA Follow Up | Sign Up & Login with Passkey
    # "webauthn",
    "totp",
    "recovery_codes",
]
# TODO: MFA Follow Up | Sign Up & Login with Passkey
MFA_PASSKEY_LOGIN_ENABLED = False
# TODO: MFA Follow Up | Sign Up & Login with Passkey
MFA_PASSKEY_SIGNUP_ENABLED = False
