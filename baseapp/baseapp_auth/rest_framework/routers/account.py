"""
isort:skip_file
"""

from baseapp_core.rest_framework.routers import DefaultRouter

account_router = DefaultRouter(trailing_slash=False)

# Register
from baseapp_auth.rest_framework.register.views import RegisterViewSet  # noqa

account_router.register(r"register", RegisterViewSet, basename="register")

# Forgot Password
from baseapp_auth.rest_framework.forgot_password.views import (
    ForgotPasswordViewSet,
    ResetPasswordViewSet,
)  # noqa

account_router.register(r"forgot-password", ForgotPasswordViewSet, basename="forgot-password")
account_router.register(r"forgot-password/reset", ResetPasswordViewSet, basename="reset-password")

# Change Email
from baseapp_auth.rest_framework.change_email.views import (
    ChangeEmailViewSet,
)  # noqa
from baseapp_auth.rest_framework.users.views import PermissionsViewSet, UsersViewSet  # noqa
from rest_framework_nested.routers import NestedSimpleRouter  # noqa

account_router.register(r"change-email", ChangeEmailViewSet, basename="change-email")

# Confirm Email
from baseapp_auth.rest_framework.confirm_email.views import (
    ConfirmEmailViewSet,
)  # noqa

account_router.register(r"confirm-email", ConfirmEmailViewSet, basename="confirm-email")

account_router.register(r"users", UsersViewSet, basename="users")

users_router_nested = NestedSimpleRouter(account_router, r"users", lookup="user")
users_router_nested.register(r"permissions", PermissionsViewSet, basename="user-permissions")

from baseapp_auth.rest_framework.change_expired_password.views import (
    ChangeExpiredPasswordViewSet,
)  # noqa

account_router.register(
    r"change-expired-password", ChangeExpiredPasswordViewSet, basename="change-expired-password"
)
