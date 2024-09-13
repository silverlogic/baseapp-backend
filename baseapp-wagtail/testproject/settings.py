from baseapp_core.tests.settings import *  # noqa

from baseapp_wagtail.settings import *  # noqa

ROOT_URLCONF = "testproject.urls"

INSTALLED_APPS += [
    # baseapp_wagtail
    "baseapp_wagtail",
]
