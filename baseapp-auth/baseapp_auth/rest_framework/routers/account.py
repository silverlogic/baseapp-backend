"""
isort:skip_file
"""

from baseapp_core.rest_framework.routers import DefaultRouter

account_router = DefaultRouter(trailing_slash=False)

# Change Email
from baseapp_auth.rest_framework.change_email.views import (
    ChangeEmailViewSet,
)  # noqa
from baseapp_auth.rest_framework.users.views import PermissionsViewSet, UsersViewSet  # noqa
from rest_framework_nested.routers import NestedSimpleRouter  # noqa

account_router.register(r"change-email", ChangeEmailViewSet, basename="change-email")

account_router.register(r"users", UsersViewSet, basename="users")

users_router_nested = NestedSimpleRouter(account_router, r"users", lookup="user")
users_router_nested.register(r"permissions", PermissionsViewSet, basename="user-permissions")

from baseapp_auth.rest_framework.change_expired_password.views import (
    ChangeExpiredPasswordViewSet,
)  # noqa

account_router.register(
    r"change-expired-password", ChangeExpiredPasswordViewSet, basename="change-expired-password"
)
