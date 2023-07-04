"""
isort:skip_file
"""

from .routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)

# Login / Register
from .login.views import LoginMfaViewSet  # noqa
from .register.views import RegisterViewSet  # noqa

router.register(r"login", LoginMfaViewSet, basename="login")
router.register(r"register", RegisterViewSet, basename="register")

# Users
from .users.views import UsersViewSet  # noqa

router.register(r"users", UsersViewSet, basename="users")

# Forgot Password
from .forgot_password.views import ForgotPasswordViewSet, ResetPasswordViewSet  # noqa

router.register(r"forgot-password", ForgotPasswordViewSet, basename="forgot-password")
router.register(r"forgot-password/reset", ResetPasswordViewSet, basename="reset-password")

# Change Email
from .change_email.views import ChangeEmailViewSet  # noqa

router.register(r"change-email", ChangeEmailViewSet, basename="change-email")
