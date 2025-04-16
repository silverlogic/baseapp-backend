import importlib

from baseapp_e2e.conf import settings


def load_script(script_name):
    module = importlib.import_module(f"{settings.SCRIPTS_PACKAGE}.{script_name}")
    module.load()
