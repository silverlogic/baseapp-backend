from baseapp_core.tests.settings import *  # noqa

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# Application definition

INSTALLED_APPS += [
    "baseapp_drf_view_action_permissions",
    "testproject.testapp",
]

MIDDLEWARE += [
    "baseapp_drf_view_action_permissions.middleware.RestrictIpMiddleware",
]

ROOT_URLCONF = "testproject.urls"
