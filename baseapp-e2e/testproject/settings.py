from baseapp_core.tests.settings import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS += [
    "baseapp_e2e",
    "testproject.testapp",
]
ROOT_URLCONF = "testproject.urls"

AUTH_USER_MODEL = "testapp.User"

# End-to-end tests
E2E = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "e2e.scripts",
}

del REST_FRAMEWORK  # noqa
