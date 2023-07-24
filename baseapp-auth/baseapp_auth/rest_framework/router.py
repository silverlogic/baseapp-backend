"""
Default router setup for auth endpoints.
"""

"""
isort:skip_file
"""

from baseapp_core.rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)

# Login / Register
from baseapp_auth.rest_framework.login.views import LoginMfaViewSet  # noqa
from baseapp_auth.rest_framework.register.views import RegisterViewSet  # noqa

router.register(r"login", LoginMfaViewSet, basename="login")
router.register(r"register", RegisterViewSet, basename="register")

# Users
from baseapp_auth.rest_framework.users.views import UsersViewSet  # noqa

router.register(r"users", UsersViewSet, basename="users")

# Forgot Password
from baseapp_auth.rest_framework.forgot_password.views import (
    ForgotPasswordViewSet,
    ResetPasswordViewSet,
)  # noqa

router.register(r"forgot-password", ForgotPasswordViewSet, basename="forgot-password")
router.register(r"forgot-password/reset", ResetPasswordViewSet, basename="reset-password")

# Change Email
from baseapp_auth.rest_framework.change_email.views import (
    ChangeEmailViewSet,
)  # noqa

router.register(r"change-email", ChangeEmailViewSet, basename="change-email")
