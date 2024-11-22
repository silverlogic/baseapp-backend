from .settings import *  # noqa

if "INSTALLED_APPS" not in globals():
    INSTALLED_APPS = []

INSTALLED_APPS += ["baseapp_wagtail.tests"]

# Constance
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
