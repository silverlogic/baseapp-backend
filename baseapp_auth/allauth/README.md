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

### 2. Configure INSTALLED_APPS

Add the following allauth apps to your `INSTALLED_APPS` in `settings/base.py`:

```python
INSTALLED_APPS = [
    # ... other apps ...
    "baseapp_auth",  # Required
    "allauth",
    "allauth.account",
    "allauth.headless",  # For headless API endpoints
    # ... rest of apps ...
]
```

### 3. Configure Authentication Backends

Add the allauth authentication backend to `AUTHENTICATION_BACKENDS`:

```python
AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
    # ... other backends ...
]
```

### 4. Add URL Patterns

In your main `urls.py` (typically `apps/urls.py`), import and include the allauth URL patterns:

```python
from baseapp_auth.allauth.urls import urlpatterns as allauth_urlpatterns

urlpatterns = [
    *allauth_urlpatterns,
    # ... other URL patterns ...
]
```

This will add:
- `/accounts/` - Web authentication endpoints (for Django admin)
- `/_allauth/` - Headless API endpoints (JSON responses)
- Admin redirects: `/admin/login/`, `/admin/logout/`, `/admin/password_change/`

### 5. Configure Allauth Settings

Add the following settings to your `settings/base.py`:

```python
# Allauth Account Settings
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = True
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
ACCOUNT_LOGIN_REDIRECT_URL = "admin:index"
ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL = "account_change_password_done"
ACCOUNT_EMAIL_VERIFICATION = "none"  # Set to "mandatory" or "optional" to enable email verification
ACCOUNT_ADAPTER = "baseapp_auth.allauth.account.adapter.AccountAdapter"

# Custom adapter settings
ALLAUTH_ADMIN_SIGNUP_ENABLED = False  # Disables public signup
ALLAUTH_ADMIN_SOCIAL_LOGIN_ENABLED = False
ALLAUTH_ADMIN_LOCALE_SELECTOR_ENABLED = False
```

### 6. Configure Headless Frontend URLs (Optional)

If you're using headless API endpoints and need to redirect users to your frontend, configure `HEADLESS_FRONTEND_URLS`:

```python
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": "https://yourfrontend.com/confirm-email/{key}",
    "account_reset_password_from_key": "https://yourfrontend.com/forgot-password/{key}",
    "account_signup": "https://yourfrontend.com/signup",
}
```

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

These endpoints return JSON and are designed for API clients:

- `POST /_allauth/login/` - Login via API
- `POST /_allauth/logout/` - Logout via API
- `POST /_allauth/signup/` - Register via API
- `POST /_allauth/password/reset/` - Request password reset
- `POST /_allauth/password/reset/confirm/` - Confirm password reset with token
- `POST /_allauth/password/change/` - Change password (authenticated)
- `POST /_allauth/email/verification/send/` - Send verification email
- `POST /_allauth/email/verification/confirm/` - Confirm email verification

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

When enabled, use the headless endpoints:
- `POST /_allauth/email/verification/send/` - Send verification email
- `POST /_allauth/email/verification/confirm/` - Confirm with token

## Password Reset Flow

### Web Flow
1. User visits `/accounts/password/reset/`
2. Submits email address
3. Receives email with reset link
4. Clicks link to `/accounts/password/reset/key/<key>/`
5. Sets new password

### Headless API Flow
1. Client sends `POST /_allauth/password/reset/` with email
2. Server sends email with token
3. Client sends `POST /_allauth/password/reset/confirm/` with token and new password
4. Server confirms password reset

## Template Customization

All allauth templates have been customized with Bootstrap 5.3.2 styling. Templates are located in:
- `baseapp_auth/allauth/templates/`

See `baseapp_auth/allauth/templates/README.md` for details on template customizations.

## Migration Notes

If you're migrating from a previous version of BaseApp:

1. **Install `django-allauth[headless]`** - The `[headless]` extra is required for API endpoints
2. **Add `allauth.headless` to INSTALLED_APPS** - This enables the `/_allauth/` endpoints
3. **Update URL configuration** - Use `*allauth_urlpatterns` from `baseapp_auth.allauth.urls`
4. **Configure `ACCOUNT_ADAPTER`** - Set to use the custom adapter
5. **Set `AUTHENTICATION_BACKENDS`** - Include `allauth.account.auth_backends.AuthenticationBackend`

## References

- [Django Allauth Documentation](https://docs.allauth.org/)
- [Django Allauth Headless Mode](https://docs.allauth.org/en/dev/headless/installation.html)
- [Django Allauth GitHub](https://github.com/pennersr/django-allauth)

