# Django Allauth Endpoints Documentation

This document lists all available authentication endpoints in the project, including django-allauth web endpoints, headless API endpoints (if configured), and legacy REST API endpoints.

## Table of Contents

1. [Django Allauth Web Endpoints](#django-allauth-web-endpoints)
2. [Not Available in This Project](#not-available-in-this-project)
3. [Django Allauth Headless API Endpoints](#django-allauth-headless-api-endpoints)
4. [Legacy REST API Endpoints](#legacy-rest-api-endpoints)
5. [Authentication Endpoints](#authentication-endpoints)
6. [Endpoint Comparison](#endpoint-comparison)

---

## Django Allauth Web Endpoints

These endpoints are provided by `allauth.urls` and return HTML templates. They are accessible at `/accounts/` prefix.

**Base URL**: `/accounts/`

### Authentication

| Endpoint | Method | Description | URL Name |
|----------|--------|-------------|----------|
| `/accounts/login/` | GET, POST | Login page | `account_login` |
| `/accounts/logout/` | GET, POST | Logout | `account_logout` |
| `/accounts/signup/` | GET, POST | User registration | `account_signup` |

### Password Management

| Endpoint | Method | Description | URL Name |
|----------|--------|-------------|----------|
| `/accounts/password/reset/` | GET, POST | Request password reset | `account_reset_password` |
| `/accounts/password/reset/done/` | GET | Password reset email sent confirmation | `account_reset_password_done` |
| `/accounts/password/reset/key/<key>/` | GET, POST | Reset password with token | `account_reset_password_from_key` |
| `/accounts/password/reset/key/done/` | GET | Password reset successful | `account_reset_password_from_key_done` |
| `/accounts/password/change/` | GET, POST | Change password (authenticated) | `account_change_password` |
| `/accounts/password/change/done/` | GET | Password change successful | `account_change_password_done` |

### Email Management

| Endpoint | Method | Description | URL Name |
|----------|--------|-------------|----------|
| `/accounts/email/` | GET, POST | Manage email addresses | `account_email` |
| `/accounts/confirm-email/` | GET | Email confirmation page | `account_email_verification_sent` |
| `/accounts/confirm-email/<key>/` | GET, POST | Confirm email with token | `account_confirm_email` |

---

## Not Available in This Project

The following django-allauth features are **not installed** in this project and their endpoints are not available:

### Social Account Management

**Status**: Not installed (`allauth.socialaccount` not in `INSTALLED_APPS`)

These endpoints would be available if `allauth.socialaccount` were added to `INSTALLED_APPS`:
- `/accounts/social/connections/` - Manage social account connections
- `/accounts/social/login/cancelled/` - Social login cancelled
- `/accounts/social/login/error/` - Social login error
- `/accounts/social/signup/` - Social account signup

### MFA (Multi-Factor Authentication)

**Status**: Not installed (`allauth.mfa` not in `INSTALLED_APPS`)

**Note**: This project uses `trench` for MFA instead of django-allauth's MFA module. See `/v1/auth/mfa/` endpoints in the Authentication Endpoints section.

These endpoints would be available if `allauth.mfa` were added to `INSTALLED_APPS`:
- `/accounts/mfa/` - MFA overview
- `/accounts/mfa/authenticate/` - MFA authentication
- `/accounts/mfa/recovery-codes/` - View/generate recovery codes
- `/accounts/mfa/totp/` - TOTP setup

### User Sessions

**Status**: Not installed (`allauth.usersessions` not in `INSTALLED_APPS`)

These endpoints would be available if `allauth.usersessions` were added to `INSTALLED_APPS`:
- `/accounts/sessions/` - List active sessions
- `/accounts/sessions/<pk>/delete/` - Delete a session

---

## Django Allauth Headless API Endpoints

**Status**: ✅ **Enabled** - Headless mode is installed and configured.

These endpoints are available at `/_allauth/` prefix and return JSON responses instead of HTML.

**Base URL**: `/_allauth/`

### Authentication

| Endpoint | Method | Description | Response Format |
|----------|--------|-------------|-----------------|
| `/_allauth/login/` | POST | Login via API | JSON |
| `/_allauth/logout/` | POST | Logout via API | JSON |
| `/_allauth/signup/` | POST | Register via API | JSON |

### Password Management

| Endpoint | Method | Description | Response Format |
|----------|--------|-------------|-----------------|
| `/_allauth/password/reset/` | POST | Request password reset | JSON |
| `/_allauth/password/reset/confirm/` | POST | Confirm password reset with token | JSON |
| `/_allauth/password/change/` | POST | Change password (authenticated) | JSON |

### Email Management

| Endpoint | Method | Description | Response Format |
|----------|--------|-------------|-----------------|
| `/_allauth/email/verification/send/` | POST | Send verification email | JSON |
| `/_allauth/email/verification/confirm/` | POST | Confirm email verification | JSON |

### Configuration

```python
# settings/base.py
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": FRONT_CONFIRM_EMAIL_URL.replace("/confirm-email/{id}/{token}", "/confirm-email/{key}"),
    "account_reset_password_from_key": FRONT_FORGOT_PASSWORD_URL.replace("/forgot-password/{token}", "/forgot-password/{key}"),
    "account_signup": FRONT_URL + "/signup" if FRONT_URL else None,
}
```

**URL Configuration**: `path("_allauth/", include("allauth.headless.urls"))` in `baseapp_auth/allauth/urls.py`

---

## Legacy REST API Endpoints

These are the current REST API endpoints provided by `baseapp_auth`. They return JSON and are accessible at `/v1/` prefix.

**Base URL**: `/v1/`

### Account Management

| Endpoint | Method | Description | ViewSet |
|----------|--------|-------------|---------|
| `/v1/register` | POST | User registration | `RegisterViewSet` |
| `/v1/forgot-password` | POST | Request password reset | `ForgotPasswordViewSet` |
| `/v1/forgot-password/reset` | POST | Reset password with token | `ResetPasswordViewSet` |
| `/v1/change-email` | POST | Request email change | `ChangeEmailViewSet` |
| `/v1/confirm-email` | PUT, POST | Confirm email verification | `ConfirmEmailViewSet` |
| `/v1/confirm-email/resend_confirm` | POST | Resend confirmation email | `ConfirmEmailViewSet.resend_confirm` |
| `/v1/change-expired-password` | POST | Change expired password | `ChangeExpiredPasswordViewSet` |

### User Management

| Endpoint | Method | Description | ViewSet |
|----------|--------|-------------|---------|
| `/v1/users` | GET, PUT | List/update users | `UsersViewSet` |
| `/v1/users/<id>/` | GET, PUT | Retrieve/update user | `UsersViewSet` |
| `/v1/users/<id>/permissions` | GET, POST | User permissions | `PermissionsViewSet` |

---

## Authentication Endpoints

These endpoints handle login and token generation.

**Base URL**: `/v1/auth/`

### JWT Authentication

| Endpoint | Method | Description | ViewSet |
|----------|--------|-------------|---------|
| `/v1/auth/jwt/login` | POST | Login with JWT | `JWTAuthViewSet.login` |
| `/v1/auth/jwt/refresh` | POST | Refresh JWT token | `JWTAuthViewSet.refresh` |

### AuthToken Authentication

| Endpoint | Method | Description | ViewSet |
|----------|--------|-------------|---------|
| `/v1/auth/authtoken/login` | POST | Login with AuthToken | `AuthTokenViewSet` |

### Pre-Auth

| Endpoint | Method | Description | ViewSet |
|----------|--------|-------------|---------|
| `/v1/auth/pre-auth/auth-token` | POST | Pre-auth with AuthToken | `PreAuthViewSet.auth_token` |
| `/v1/auth/pre-auth/jwt` | POST | Pre-auth with JWT | `PreAuthViewSet.jwt` |

### MFA Authentication

| Endpoint | Method | Description | ViewSet |
|----------|--------|-------------|---------|
| `/v1/auth/mfa/login` | POST | Login with MFA (AuthToken) | `MfaAuthTokenViewSet` |
| `/v1/auth/mfa/jwt/login` | POST | Login with MFA (JWT) | `MfaJwtViewSet` |

---

## Admin Redirects

These are custom redirects that forward Django admin authentication URLs to django-allauth.

| Original URL | Redirects To | Permanent |
|--------------|--------------|-----------|
| `/admin/login/` | `/accounts/login/` | No |
| `/admin/logout/` | `/accounts/logout/` | Yes |
| `/admin/password_change/` | `/accounts/password/change/` | Yes |
| `/admin/password_change/done/` | `/admin/` | Yes |

**Location**: Defined in `baseapp_auth/allauth/urls.py`

---

## Endpoint Comparison

### Password Reset

| System | Request Endpoint | Reset Endpoint | Format |
|--------|-----------------|----------------|--------|
| **Django Allauth (Web)** | `POST /accounts/password/reset/` | `POST /accounts/password/reset/key/<key>/` | HTML Forms |
| **Django Allauth (Headless)** | `POST /_allauth/password/reset/` | `POST /_allauth/password/reset/confirm/` | JSON |
| **Legacy REST API** | `POST /v1/forgot-password` | `POST /v1/forgot-password/reset` | JSON |

### Email Verification

| System | Request Endpoint | Confirm Endpoint | Format |
|--------|------------------|------------------|--------|
| **Django Allauth (Web)** | N/A (automatic on signup) | `GET /accounts/confirm-email/<key>/` | HTML |
| **Django Allauth (Headless)** | `POST /_allauth/email/verification/send/` | `POST /_allauth/email/verification/confirm/` | JSON |
| **Legacy REST API** | `POST /v1/confirm-email/resend_confirm` | `PUT /v1/confirm-email/<id>/` | JSON |

### User Registration

| System | Endpoint | Format | Notes |
|--------|----------|--------|-------|
| **Django Allauth (Web)** | `POST /accounts/signup/` | HTML Form | Uses allauth adapter |
| **Django Allauth (Headless)** | `POST /_allauth/signup/` | JSON | Uses allauth adapter |
| **Legacy REST API** | `POST /v1/register` | JSON | Custom implementation |

---

## Current Configuration

### Django Allauth Settings

```python
# settings/base.py
ACCOUNT_EMAIL_VERIFICATION = "none"  # Email verification disabled
ACCOUNT_ADAPTER = "baseapp_auth.allauth.account.adapter.AccountAdapter"
ALLAUTH_ADMIN_SIGNUP_ENABLED = False  # Signup disabled via adapter
```

### Installed Allauth Apps

The following django-allauth apps are installed in this project:
- `allauth` - Core allauth functionality
- `allauth.account` - Account management (login, signup, password reset, email management)
- `allauth.headless` - Headless API mode (✅ enabled)

**Not installed:**
- `allauth.socialaccount` - Social authentication (Google, Facebook, etc.)
- `allauth.mfa` - Multi-factor authentication (project uses `trench` instead)
- `allauth.usersessions` - User session management

### URL Configuration

- **Web endpoints**: `path("accounts/", include("allauth.urls"))` in `baseapp_auth/allauth/urls.py`
- **Headless API endpoints**: `path("_allauth/", include("allauth.headless.urls"))` in `baseapp_auth/allauth/urls.py`
- **Legacy REST API**: `re_path(r"", include(account_router.urls))` in `apps/urls.py` (v1 namespace)

---

## Notes

1. **Web endpoints** (`/accounts/`) are primarily for Django admin authentication and return HTML templates.
2. **Headless API endpoints** (`/_allauth/`) provide JSON-based authentication for API clients.
3. **Legacy REST API endpoints** (`/v1/*`) are currently active and used by mobile/web clients.
4. The project uses a **custom `AccountAdapter`** that:
   - Disables public signup by default
   - Redirects to Django admin after login
   - Handles password change redirects

---

## References

- [Django Allauth Documentation](https://docs.allauth.org/)
- [Django Allauth Headless Mode](https://docs.allauth.org/en/dev/headless/installation.html)
- [Django Allauth GitHub](https://github.com/pennersr/django-allauth)

