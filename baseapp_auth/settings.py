from baseapp_core.settings.env import env

ALLAUTH_AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
]

ALLAUTH_HEADLESS_INSTALLED_APPS = [
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "rest_framework_simplejwt.token_blacklist",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

ALLAUTH_HEADLESS_MIDDLEWARE = [
    "allauth.account.middleware.AccountMiddleware",
]

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_SIGNUP_FORM_CLASS = "baseapp_auth.allauth.account.forms.CustomAllauthSignupForm"
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "baseapp_auth.allauth.account.adapter.AccountAdapter"

ALLAUTH_ADMIN_SIGNUP_ENABLED = False
ALLAUTH_ADMIN_SOCIAL_LOGIN_ENABLED = False
ALLAUTH_ADMIN_LOCALE_SELECTOR_ENABLED = False

HEADLESS_TOKEN_STRATEGY = "baseapp_auth.tokens.AllAuthUserProfileJWTTokenStrategy"
HEADLESS_SERVE_SPECIFICATION = env("HEADLESS_SERVE_SPECIFICATION", default=False, required=False)

HEADLESS_JWT_PRIVATE_KEY = env("HEADLESS_JWT_PRIVATE_KEY")
HEADLESS_JWT_PUBLIC_KEY = env("HEADLESS_JWT_PUBLIC_KEY")
HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN = 300
HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN = 86400
HEADLESS_JWT_AUTHORIZATION_HEADER_SCHEME = "Bearer"
HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED = True
HEADLESS_JWT_ROTATE_REFRESH_TOKEN = True
HEADLESS_JWT_ALGORITHM = "RS256"

SIMPLE_JWT = {
    "TOKEN_OBTAIN_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtLoginSerializer",
    "TOKEN_REFRESH_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtRefreshSerializer",
    "ALGORITHM": HEADLESS_JWT_ALGORITHM,
    "VERIFYING_KEY": HEADLESS_JWT_PUBLIC_KEY,
    "SIGNING_KEY": HEADLESS_JWT_PRIVATE_KEY,
    "AUTH_HEADER_TYPES": (HEADLESS_JWT_AUTHORIZATION_HEADER_SCHEME,),
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_CLAIM": "sub",
}

JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"

# Social Account Configuration
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_QUERY_EMAIL = True

# Google Provider Configuration
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        # For AllAuth Headless with provider/token endpoint,
        # we don't use PKCE as we're sending id_token directly
        "OAUTH_PKCE_ENABLED": False,
        # Enable token verification
        "VERIFIED_EMAIL": True,
    }
}

GRAPHQL_WS_CONSUMER = "baseapp_core.graphql.consumers.GraphqlWsJWTAuthenticatedConsumer"

GRAPHQL_JWT_AUTHENTICATION_MIDDLEWARE = "baseapp_core.graphql.middlewares.JWTAuthentication"