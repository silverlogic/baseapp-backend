from baseapp_core.tests.settings import *  # noqa

ROOT_URLCONF = "testproject.urls"

# Application definition
INSTALLED_APPS += [
    "baseapp_url_shortening",
]

URL_SHORTENING_PREFIX = "c"
