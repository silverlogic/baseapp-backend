# BaseApp Auth

## Usage

This project provides the default User model and authentication utilities.

### Abstract user model

`AbstractUser` is an abstract Django user model implementation. It provides a default implementation of `User` model and can be extended in the target Django app. The attached [test project](testproject/) contains a concrete implementation of User class for demo purposes.

### Authentication endpoints

In `rest_framework` directory you can find a implementation of authentication-related endpoints: login, signup, forgot-passowrd, change-email. The attached [test project](testproject/) has DRF routing set up to test/demo JWT authentication and Multi-factor authentication (MFA).
[README.md](..%2Fbaseapp-referrals%2FREADME.md)
### Utilities

## How to use

There is a [standalon demo project](testproject/) with a complete demo setup.

### Installation

Add to requirements of yor project (replacing everything inside brackets):

```bash
baseapp-auth @ git+https://github.com/silverlogic/baseapp-backend.git@v0.1#subdirectory=baseapp-auth
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

and set the required `SIMPLE_JWT` settings (e.g. the claims serializer):

```py
SIMPLE_JWT = {
    # It will work instead of the default serializer(TokenObtainPairSerializer).
    "TOKEN_OBTAIN_SERIALIZER": "testproject.testapp.rest_framework.jwt.serializers.MyTokenObtainPairSerializer",
    # ...
}
```

There is a constance config for password expiration interval:

```py
CONSTANCE_CONFIG = OrderedDict(
    [
        (
            "USER_PASSWORD_EXPIRATION_INTERVAL",
            (
                365 * 2,
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
