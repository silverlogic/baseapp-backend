# BaseApp Auth

## Usage

This project includes:

- API endpoints for authentication and account management
- default User model

### Abstract user model

`AbstractUser` is an abstract Django user model implementation. It provides a default implementation of `User` model and can be extended in the target Django app. The attached [test project](testproject/) contains a concrete implementation of User class for demo purposes.

### Authentication endpoints

In the `rest_framework/` directory you can find a implementation of account-related endpoints: login, signup, forgot-passowrd, change-email. Authentication (login) is implemented in a few different modes that can be picked depending on project preference/requirements. In [testproject/urls.py](testproject/urls.py) you'll find DRF routing set up for each of supported modes with unit tests for each mode:

- Authentication with Simple AuthToken (deprecated for headless clients)
- Authentication with JWT (deprecated - use allauth.headless instead)
- Authentication with MFA and Simple AuthToken
- Authentication with MFA and JWT

#### Headless AllAuth API Endpoints

**⚠️ IMPORTANT: We now use the official `allauth.headless` module for headless authentication.**

The package provides headless authentication endpoints using django-allauth's official headless module (`allauth.headless`). These endpoints use OAuth2-style JWT tokens (access and refresh tokens) and are designed for frontend applications.

**Official AllAuth Headless Endpoints (Recommended):**

- `POST /v1/_allauth/app/v1/auth/signup` - User registration (signup)
- `POST /v1/_allauth/app/v1/auth/login` - User login
- `DELETE /v1/_allauth/app/v1/auth/session` - User logout
- `POST /v1/_allauth/app/v1/tokens/refresh` - Token refresh
- `POST /v1/_allauth/app/v1/auth/password/request` - Request password reset

**⚠️ Legacy Custom Endpoints (Deprecated):**

The following custom endpoints are deprecated and will be removed in a future version:

- `POST /v1/register` - Use `/v1/_allauth/app/v1/auth/signup` instead
- `POST /v1/auth/jwt/login` - Use `/v1/_allauth/app/v1/auth/login` instead
- `POST /v1/auth/jwt/refresh` - Use `/v1/_allauth/app/v1/tokens/refresh` instead

**OAuth2 Flow:**

The implementation follows OAuth2-style token flow:

1. **Signup/Login**: Client receives access token (short-lived, ~5 minutes) and refresh token (long-lived, ~1 day)
2. **API Requests**: Client includes access token in `Authorization: Bearer <token>` header
3. **Token Refresh**: When access token expires, client exchanges refresh token for new tokens
4. **Logout**: Client calls logout endpoint, which invalidates tokens

**Token Lifecycle:**

- Access tokens are short-lived (default: 5 minutes) and used for API authentication
- Refresh tokens are long-lived (default: 1 day) and used to obtain new access tokens
- Tokens are invalidated on logout via session deletion (stateful validation enabled)
- When refresh tokens are rotated, old tokens are invalidated

**Configuration:**

```python
from baseapp_auth.settings import (
    ACCOUNT_ADAPTER,
    ACCOUNT_AUTHENTICATION_METHOD,
    ACCOUNT_EMAIL_VERIFICATION,
    ACCOUNT_SIGNUP_FIELDS,
    ACCOUNT_SIGNUP_FORM_CLASS,
    ACCOUNT_USER_MODEL_USERNAME_FIELD,
    ALLAUTH_ADMIN_LOCALE_SELECTOR_ENABLED,
    ALLAUTH_ADMIN_SIGNUP_ENABLED,
    ALLAUTH_ADMIN_SOCIAL_LOGIN_ENABLED,
    ALLAUTH_HEADLESS_INSTALLED_APPS,
    ALLAUTH_HEADLESS_MIDDLEWARE,
    HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN,
    HEADLESS_JWT_AUTHORIZATION_HEADER_SCHEME,
    HEADLESS_JWT_PRIVATE_KEY,
    HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN,
    HEADLESS_JWT_ROTATE_REFRESH_TOKEN,
    HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED,
    HEADLESS_TOKEN_STRATEGY,
    JWT_CLAIM_SERIALIZER_CLASS,
    SIMPLE_JWT,
)

INSTALLED_APPS += [
    *ALLAUTH_HEADLESS_INSTALLED_APPS,
    "baseapp_auth",
]

MIDDLEWARE += [
    *ALLAUTH_HEADLESS_MIDDLEWARE,
]

AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_auth.permissions.UsersPermissionsBackend",
]

SITE_ID = 1
ACCOUNT_LOGIN_REDIRECT_URL = "admin:index"
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL = "account_change_password_done"

HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONT_URL}/confirm-email/{{key}}",
    "account_reset_password_from_key": f"{FRONT_URL}/forgot-password/{{key}}",
    "account_signup": f"{FRONT_URL}/signup",
}
```

Generate and configure JWT private and public keys:

```bash
openssl genpkey -algorithm RSA -out private_key.pem -pkeyopt rsa_keygen_bits:2048
openssl rsa -pubout -in private_key.pem -out public_key.pem

cat private_key.pem
cat public_key.pem
```

Add to `.env`:

```bash
HEADLESS_JWT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg...\n-----END PRIVATE KEY-----"
HEADLESS_JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhki...\n-----END PUBLIC KEY-----"
```

**Important**: A valid private key is required. The headless endpoints will fail with a 500 error if the key is missing or invalid.

Include URLs:

```python
urlpatterns = [
    path("_allauth/", include("allauth.headless.urls")),
]
```

**Using the API:**

Authenticated requests use JWT access tokens:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

When access token expires, exchange refresh token for new tokens via `/v1/_allauth/app/v1/tokens/refresh`.

**Configure REST Framework:**

The template includes `JWTTokenAuthentication` in `REST_FRAMEWORK` by default. If setting up from scratch, add it to your `settings/base.py`:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "allauth.headless.contrib.rest_framework.authentication.JWTTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        # Add other authentication classes as needed
    ),
    # ... other REST_FRAMEWORK settings
}
```

**Protect DRF endpoints:**

For individual views, you can specify authentication classes:

```python
from allauth.headless.contrib.rest_framework.authentication import JWTTokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

class YourAPIView(APIView):
    authentication_classes = [JWTTokenAuthentication]
    permission_classes = [IsAuthenticated]
```

Or rely on the default authentication classes configured in `REST_FRAMEWORK`.

See [django-allauth documentation](https://docs.allauth.org/en/dev/headless/) for more details.

### GraphQL

#### WebSocket Consumer

The `GRAPHQL_WS_CONSUMER` setting is automatically available (imported from `baseapp_auth.settings`). It defaults to `baseapp_core.graphql.consumers.GraphqlWsJWTAuthenticatedConsumer` (simplejwt).

When using allauth headless JWT authentication with GraphQL WebSockets, override the setting in your `settings/base.py`:

```python
GRAPHQL_WS_CONSUMER = "baseapp_auth.graphql.consumers.GraphqlWsAllAuthJWTAuthenticatedConsumer"
```

#### JWT Authentication Middleware

The `GRAPHQL_JWT_AUTHENTICATION_MIDDLEWARE` setting is automatically available (imported from `baseapp_auth.settings`). It defaults to `baseapp_core.graphql.middlewares.JWTAuthentication` (simplejwt).

When using allauth headless JWT authentication with GraphQL HTTP queries, override the setting in your `settings/base.py`:

```python
GRAPHQL_JWT_AUTHENTICATION_MIDDLEWARE = "baseapp_auth.graphql.middlewares.AllauthJWTTokenAuthentication"
```

This setting is used in the `GRAPHENE["MIDDLEWARE"]` configuration.

#### PermissionsInterface

When your `DjangoObjectType` implements `PermissionsInterface` you are able to query for object-level permissions:

```graphql
query {
  page(id: 1) {
    canDelete: hasPerm(perm: "delete")
    canChange: hasPerm(perm: "change")
  }
}
```

### Utilities

## Demo

There is a [test project](testproject/) with a complete demo set up.

## Installation

Install in your environment:

```bash
pip install baseapp-backend[auth]
```

### Settings

Add the app to your project INSTALLED_APPS:

```py
INSTALLED_APPS = [
    ...
    "baseapp_auth",
]
```

Set the Django auth user model to the concrete model of your app:

```py
AUTH_USER_MODEL = "testapp.User"
```

If you want to use JWT authentication, add the corresponding authentication backend:

```py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        # ...
    )
}
```

I you want to use JWT authentication, set the related JWT settings (e.g. the claims serializer):

```py
SIMPLE_JWT = {
    # It will work instead of the default serializer(TokenObtainPairSerializer).
    "TOKEN_OBTAIN_SERIALIZER": "testproject.testapp.rest_framework.jwt.serializers.MyTokenObtainPairSerializer",
    # ...
}
JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"
```

We override some settings from the Simple JWT library by default to make some baseapp features work properly. They look like the following:

```py
SIMPLE_JWT = {
    "TOKEN_OBTAIN_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtLoginSerializer",
    "TOKEN_REFRESH_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtRefreshSerializer",
}

JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"
```

However, any setting defined on the project will take precedence over the default ones.

There is a constance config for password expiration interval:

```py
CONSTANCE_CONFIG = OrderedDict(
    [
        (
            "USER_PASSWORD_EXPIRATION_INTERVAL",
            (
                0,
                "The time interval (in days) after which a user will need to reset their password.",
            ),
        ),
    ]
)
```

There is an optional scheduled task that can be configured for notifying that the user's password has expired:

```py
CELERY_BEAT_SCHEDULE = {
    "notify_is_password_expired": {
        "task": "baseapp_auth.tasks.notify_users_is_password_expired",
        "schedule": "...",
        "options": "...",
    },
}
```

## How to delevop

General development instructions can be found in [main README](..#testing)

## Other Settings

```py
BA_AUTH_PRE_AUTH_TOKEN_EXPIRATION_TIME_DELTA: datetime.timedelta
BA_AUTH_CHANGE_EXPIRED_PASSWORD_TOKEN_EXPIRATION_TIME_DELTA: datetime.timedelta
BA_AUTH_CONFIRM_EMAIL_TOKEN_EXPIRATION_TIME_DELTA: datetime.timedelta
BA_AUTH_CHANGE_EMAIL_VERIFY_TOKEN_EXPIRATION_TIME_DELTA: datetime.timedelta
BA_AUTH_CHANGE_EMAIL_CONFIRM_TOKEN_EXPIRATION_TIME_DELTA: datetime.timedelta
```
