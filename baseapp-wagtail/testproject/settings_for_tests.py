from .settings import *  # noqa

INSTALLED_APPS = INSTALLED_APPS + ["baseapp_wagtail.tests"]

# Constance
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
