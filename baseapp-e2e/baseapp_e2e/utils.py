from baseapp_e2e.conf import settings


def load_script(script_name):
    __import__(f"{settings.SCRIPTS_PACKAGE}.{script_name}")
