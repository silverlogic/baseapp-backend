# BaseApp Auth

## Usage

This project includes:

- API endpoints for authentication and account management
- default User model

### Abstract user model

`AbstractUser` is an abstract Django user model implementation. It provides a default implementation of `User` model and can be extended in the target Django app. The attached [test project](testproject/) contains a concrete implementation of User class for demo purposes.

### Authentication endpoints

In the `rest_framework/` directory you can find a implementation of account-related endpoints: login, signup, forgot-passowrd, change-email. Authentication (login) is implemented in a few different modes that can be picked depending on project preference/requirements. In [testproject/urls.py](testproject/urls.py) you'll find DRF routing set up for each of supported modes with unit tests for each mode:

- Authentication with Simple AuthToken
- Authentication with JWT
- Authentication with MFA and Simple AuthToken
- Authentication with MFA and JWT

#### Users

`GET /v1/users/me` and `GET /v1/users/<id>` return the user. When the user reads their own record the
response also has the private fields (`email`, `first_name`, `last_name`, `preferred_language`, ...);
other users only see `id`, `profile` and `phone_number`. A user updates their own record with
`PATCH /v1/users/<id>`, e.g. `{"first_name": "Ada", "last_name": "Lovelace"}`. The profile name
follows the user's name, and the response already carries the new profile name.

#### MFA endpoints

MFA is built on [django-trench](https://github.com/merixstudio/django-trench). With the MFA routes
mounted under `/v1/auth/mfa/` (as the auth plugin does), the endpoints are:

| Method | Path | Auth | Body | What it does |
|---|---|---|---|---|
| POST | `/v1/auth/mfa/login` | none | `email`, `password` | Login step 1. Sends a code through the user's primary method and returns `ephemeral_token` and `method`; returns the auth token straight away when the user has no MFA method. |
| POST | `/v1/auth/mfa/login/code` | none | `ephemeral_token`, `code` | Login step 2. Returns the auth token. |
| POST | `/v1/auth/mfa/jwt/login` | none | `email`, `password` | Same as step 1, for JWT. |
| POST | `/v1/auth/mfa/jwt/login/code` | none | `ephemeral_token`, `code` | Same as step 2; returns `access` and `refresh`. |
| POST | `/v1/auth/mfa/code/request/` | user | `method` (optional, defaults to the primary method) | Sends a new code to a signed-in user, e.g. before deactivating a method or changing the primary one. `GET` is not allowed. |
| POST | `/v1/auth/mfa/<method>/activate/` | user | | Starts activating `method` (sends a code, or returns the QR link for `app`). |
| POST | `/v1/auth/mfa/<method>/activate/confirm/` | user | `code` | Activates `method` and returns its `backup_codes`. |
| POST | `/v1/auth/mfa/<method>/deactivate/` | user | `code` (see below) | Deactivates `method`. |
| POST | `/v1/auth/mfa/<method>/codes/regenerate/` | user | `code` | Returns new `backup_codes`. |
| POST | `/v1/auth/mfa/change-primary-method/` | user | `method`, `code` (of the new method) | Makes `method` the primary one. |
| GET | `/v1/auth/mfa/user-active-methods/` | user | | Lists the user's active methods. |
| GET | `/v1/auth/mfa/config/` | none | | The available methods and trench's code settings. |

The login code is sent by login step 1. `code/request/` needs a signed-in user, so during login a new
code is requested by posting the credentials to step 1 again.

#### MFA signals

`baseapp_auth.rest_framework.mfa.signals` has a signal for each change a user can make. They are sent
after the change succeeds, with `sender` set to the view class and the keyword arguments `user`,
`method` (the method name, e.g. `"app"`) and `request`:

- `mfa_method_activated`: a method's activation was confirmed.
- `mfa_method_deactivated`: a method was deactivated.
- `mfa_primary_method_changed`: another method became primary; also sends `previous_method`
  (`None` when there was none). Not sent when the request names the method that is already primary.
- `mfa_backup_codes_regenerated`: a method's backup codes were regenerated.

```py
import logging

from django.dispatch import receiver

from baseapp_auth.rest_framework.mfa.signals import mfa_method_deactivated

logger = logging.getLogger(__name__)


@receiver(mfa_method_deactivated)
def log_mfa_deactivation(sender, user, method, request, **kwargs):
    logger.info("User %s deactivated MFA method %s", user.pk, method)
```

#### MFA policy

The deactivate and change-primary views ask a policy first. Point `BASEAPP_AUTH_MFA_POLICY` at a
subclass of `baseapp_auth.rest_framework.mfa.policy.MFAPolicy`:

- `is_required(user) -> bool`: whether the user must keep MFA on. Default `False`.
- `can_deactivate(user, method) -> (bool, reason)`: by default refuses only when `is_required(user)`
  is true and `method` is the user's last active method.
- `can_change_primary(user, method) -> (bool, reason)`: default allows.

A refusal is a `400` with `{"non_field_errors": [reason]}`. When `is_required(user)` is true, the
deactivate view also requires a `code` of the method (or a backup code), even if trench's
`CONFIRM_DISABLE_WITH_CODE` is off. The default policy allows everything, as before.

The views lock the user's MFA methods (`SELECT ... FOR UPDATE`) before asking the policy and keep
the lock until the change is saved, so two requests at once can't both remove a method and leave a
user who must keep MFA with none. A refused change doesn't use up the backup code it was sent with.
`is_required` can be called more than once per request: keep it cheap, and give the same answer
for the same user.

```py
# settings.py
BASEAPP_AUTH_MFA_POLICY = "myproject.users.mfa.StaffMFAPolicy"

# myproject/users/mfa.py
from baseapp_auth.rest_framework.mfa.policy import MFAPolicy


class StaffMFAPolicy(MFAPolicy):
    def is_required(self, user):
        return user.is_staff
```

#### Replacing an MFA view

`baseapp_auth.rest_framework.urls.mfa` reads its views from `BASEAPP_AUTH_MFA_VIEWS`, so you can
subclass one view and keep the URL list. The keys are `activate`, `activate_confirm`, `deactivate`,
`regenerate_codes`, `request_code`, `config`, `user_active_methods` and `change_primary_method`; the
values are classes or dotted paths. Unknown keys raise `ImproperlyConfigured`.

```py
BASEAPP_AUTH_MFA_VIEWS = {
    "activate": "myproject.users.mfa.PhoneCheckingActivationView",
}
```

Subclass the defaults in `baseapp_auth.rest_framework.mfa.views` (or trench's views for `activate`,
`request_code`, `config` and `user_active_methods`) so the signals and the policy keep working.

The setting is read once, when `baseapp_auth.rest_framework.urls.mfa` is imported. Changing it later,
including with `override_settings` in tests, doesn't change the mounted views; call
`baseapp_auth.rest_framework.urls.mfa.get_urlpatterns()` to build the URLs from the current value.


### GraphQL

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

### Impersonation

`baseapp_auth.impersonation` is an opt-in app that lets an authorized user act as another user
for a limited time, read-only by default, with every session (and, in act-as mode, every write)
recorded. See [impersonation/README.md](impersonation/README.md).

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
BASEAPP_AUTH_MFA_POLICY: str  # dotted path to an MFAPolicy subclass, see "MFA policy"; default allows all
BASEAPP_AUTH_MFA_VIEWS: dict[str, str | type]  # see "Replacing an MFA view"; default {}
```
