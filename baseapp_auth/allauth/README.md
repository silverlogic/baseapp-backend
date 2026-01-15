# Django Allauth Integration

This package provides django-allauth integration for BaseApp projects, including web authentication endpoints for Django admin and headless API endpoints for mobile/web clients.

## Requirements

- `baseapp_auth` must be installed in your project
- `django-allauth[headless]` version 65.13.0 or higher

## Installation

### 1. Install Dependencies

Add `django-allauth[headless]` to your project dependencies. If using `baseapp-backend` package:

```python
# setup.cfg or requirements.txt
django-allauth[headless] == 65.13.0
```

### 2. Configure Settings

Import all allauth configuration from `baseapp_auth.settings` in your `settings/base.py`:

```python
from baseapp_auth.settings import *  # noqa
from baseapp_auth.settings import (
    ALLAUTH_AUTHENTICATION_BACKENDS,
    ALLAUTH_HEADLESS_INSTALLED_APPS,
    ALLAUTH_HEADLESS_MIDDLEWARE,
)

INSTALLED_APPS = [
    *ALLAUTH_HEADLESS_INSTALLED_APPS,
    # ... your other apps ...
]

MIDDLEWARE = [
    *ALLAUTH_HEADLESS_MIDDLEWARE,
    # ... your other middleware ...
]

AUTHENTICATION_BACKENDS = [
    *ALLAUTH_AUTHENTICATION_BACKENDS,  # Allauth backends first
    # ... your other backends ...
]
```

**Note:** The order of `AUTHENTICATION_BACKENDS` matters. Django checks backends in order, and the first one that successfully authenticates a user wins. Allauth backends should be placed first to ensure email verification and other allauth-specific authentication rules are properly enforced (e.g., when `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`).

This will automatically configure all allauth settings including:

- Required apps: `django.contrib.sites`, `allauth`, `allauth.account`, `allauth.headless`, `rest_framework_simplejwt.token_blacklist`
- Required middleware: `allauth.account.middleware.AccountMiddleware`
- Required authentication backend: `allauth.account.auth_backends.AuthenticationBackend`
- Account settings: authentication method, email verification, signup configuration
- Headless JWT settings: token strategies, expiration times, rotation policies
- Custom adapter settings: signup, social login, and locale selector configuration

**Note:** You can override any of these settings by redefining them after the imports. For example:

```python
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN = 600
```

### 3. Add URL Patterns

In your main `urls.py` (typically `apps/urls.py`), import and include the allauth URL patterns:

```python
from django.urls import include, path, re_path
from baseapp_auth.allauth.urls import (
    allauth_admin_urls,
    allauth_headless_urls,
)

v1_urlpatterns = [
    # ... other v1 API endpoints ...
    re_path(r"", include(allauth_headless_urls)),
]

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    path("v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
    path("", include(allauth_admin_urls)),
    # ... other URL patterns ...
]
```

**Note:** The order of URL patterns matters. The allauth admin URLs should be placed **after** the Django admin URL pattern (`re_path(r"^admin/", admin.site.urls)`) but can be placed before or after other app URLs depending on your routing needs.

This will add:

- `/accounts/` - Web authentication endpoints (for Django admin) - at root level
- `/v1/_allauth/` - Headless API endpoints (JSON responses) - under v1 namespace
- Admin redirects: `/admin/login/`, `/admin/logout/`, `/admin/password_change/` - at root level

### 4. Configure Additional Allauth Settings

Add the following settings to your `settings/base.py`:

```python
SITE_ID = 1
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
ACCOUNT_LOGIN_REDIRECT_URL = "admin:index"
ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL = "account_change_password_done"

HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": "https://yourfrontend.com/confirm-email/{key}",
    "account_reset_password_from_key": "https://yourfrontend.com/forgot-password/{key}",
    "account_signup": "https://yourfrontend.com/signup",
}
```

**Note:** Most allauth settings are already configured by importing from `baseapp_auth.settings`. The settings above are project-specific customizations for redirect URLs and frontend URLs.

## Available Endpoints

### Web Endpoints (HTML)

These endpoints are primarily used for Django admin authentication:

- `/accounts/login/` - Login page
- `/accounts/logout/` - Logout
- `/accounts/password/reset/` - Request password reset
- `/accounts/password/reset/key/<key>/` - Reset password with token
- `/accounts/password/change/` - Change password (authenticated)
- `/accounts/email/` - Manage email addresses
- `/accounts/confirm-email/<key>/` - Confirm email verification

### Headless API Endpoints (JSON)

These endpoints return JSON and are designed for API clients. When included in the v1 namespace, they are available at `/v1/_allauth/`:

- `POST /v1/_allauth/login/` - Login via API
- `POST /v1/_allauth/logout/` - Logout via API
- `POST /v1/_allauth/signup/` - Register via API
- `POST /v1/_allauth/password/reset/` - Request password reset
- `POST /v1/_allauth/password/reset/confirm/` - Confirm password reset with token
- `POST /v1/_allauth/password/change/` - Change password (authenticated)
- `POST /v1/_allauth/email/verification/send/` - Send verification email
- `POST /v1/_allauth/email/verification/confirm/` - Confirm email verification

### Admin Redirects

The following Django admin URLs are automatically redirected to allauth:

- `/admin/login/` → `/accounts/login/`
- `/admin/logout/` → `/accounts/logout/`
- `/admin/password_change/` → `/accounts/password/change/`
- `/admin/password_change/done/` → `/admin/`

## Custom Account Adapter

The project uses a custom `AccountAdapter` (`baseapp_auth.allauth.account.adapter.AccountAdapter`) that:

- Disables public signup by default (controlled by `ALLAUTH_ADMIN_SIGNUP_ENABLED`)
- Redirects users to Django admin after login
- Validates redirect URLs to prevent open redirect vulnerabilities
- Handles password change redirects

## Email Verification

Email verification can be configured via `ACCOUNT_EMAIL_VERIFICATION`:

- `"none"` - Email verification disabled (default)
- `"optional"` - Users can log in without verifying, but verification is available
- `"mandatory"` - Users must verify their email before logging in

**Important**: When `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`, users with unverified emails cannot obtain access tokens via the login endpoint. The allauth authentication backend automatically enforces this restriction.

When enabled, use the headless endpoints:

- `POST /v1/_allauth/email/verification/send/` - Send verification email
- `POST /v1/_allauth/email/verification/confirm/` - Confirm with token

### Enabling Email Verification

To require email verification, set in `settings/base.py`:

```python
ACCOUNT_EMAIL_VERIFICATION = "mandatory"  # Require verification before login
# or
ACCOUNT_EMAIL_VERIFICATION = "optional"   # Allow login without verification
```

No code changes are required - this is controlled entirely via settings.

## Password Reset Flow

### Web Flow

1. User visits `/accounts/password/reset/`
2. Submits email address
3. Receives email with reset link
4. Clicks link to `/accounts/password/reset/key/<key>/`
5. Sets new password

### Headless API Flow

1. Client sends `POST /v1/_allauth/password/reset/` with email
2. Server sends email with token
3. Client sends `POST /v1/_allauth/password/reset/confirm/` with token and new password
4. Server confirms password reset
5. User can log in with new password using `POST /v1/_allauth/login/`
6. Old password no longer works (automatically invalidated by Django)

### Password Reset API Usage

**Request Password Reset:**

```bash
POST /v1/_allauth/password/reset/
Content-Type: application/json

{
  "email": "user@example.com"
}
```

**Response** (always returns success, even if email doesn't exist - security best practice):

```json
{
  "status": 200,
  "message": "Password reset email sent"
}
```

**Confirm Password Reset:**

```bash
POST /v1/_allauth/password/reset/confirm/
Content-Type: application/json

{
  "key": "reset-token-from-email",
  "password": "new-secure-password"
}
```

**Response** (success):

```json
{
  "status": 200,
  "message": "Password reset successful"
}
```

**Error Responses:**

- Invalid or expired token: Returns 400 with error message
- Unknown user: Returns generic error (does not leak email existence)
- All errors are machine-readable JSON format

## Template Customization

All allauth templates have been customized with Bootstrap 5.3.2 styling. Templates are located in:

- `baseapp_auth/allauth/templates/`

See `baseapp_auth/allauth/templates/README.md` for details on template customizations.

## Migration Notes

If you're migrating from a previous version of BaseApp:

1. **Install `django-allauth[headless]`** - The `[headless]` extra is required for API endpoints
2. **Import allauth configuration constants** - Use `ALLAUTH_HEADLESS_INSTALLED_APPS`, `ALLAUTH_HEADLESS_MIDDLEWARE`, and `ALLAUTH_AUTHENTICATION_BACKENDS` from `baseapp_auth.settings`
3. **Update URL configuration** - Import `allauth_admin_urls` and `allauth_headless_urls` separately. Place `allauth_headless_urls` in your v1 API patterns and `allauth_admin_urls` at root level as shown in the installation guide
4. **Configure additional settings** - Set `SITE_ID`, redirect URLs, and `HEADLESS_FRONTEND_URLS` as needed

## References

- [Django Allauth Documentation](https://docs.allauth.org/)
- [Django Allauth Headless Mode](https://docs.allauth.org/en/dev/headless/installation.html)
- [Django Allauth GitHub](https://github.com/pennersr/django-allauth)
