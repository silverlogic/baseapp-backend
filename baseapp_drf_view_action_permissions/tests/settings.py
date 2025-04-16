from testproject.settings import *  # noqa

INSTALLED_APPS = INSTALLED_APPS + [
    "baseapp_drf_view_action_permissions",
    "baseapp_drf_view_action_permissions.tests",
]
INSTALLED_APPS.remove("testproject.users")

AUTH_USER_MODEL = "baseapp_drf_view_action_permissions_tests.DRFUser"

MIDDLEWARE = MIDDLEWARE + [
    "baseapp_drf_view_action_permissions.middleware.RestrictIpMiddleware",
]
