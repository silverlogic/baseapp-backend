from baseapp_core.tests.settings import *  # noqa
from django.utils.translation import gettext_lazy as _

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# Application definition

INSTALLED_APPS += [
    "baseapp_message_templates",
]

ROOT_URLCONF = "testproject.urls"

LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]
