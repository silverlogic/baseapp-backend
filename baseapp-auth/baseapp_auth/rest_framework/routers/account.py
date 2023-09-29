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

account_router.register(r"change-email", ChangeEmailViewSet, basename="change-email")
