from baseapp_core.tests.settings import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# Application definition

INSTALLED_APPS += [
    "baseapp_message_templates",
]


ROOT_URLCONF = "testproject.urls"
