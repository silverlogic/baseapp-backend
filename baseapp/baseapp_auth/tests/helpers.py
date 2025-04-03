import importlib
import json

from django.conf import settings

from baseapp_core.tests.helpers import *  # noqa: F403, F401


def get_json(data):
    return json.loads(json.dumps(data))


def get_user_factory():
    factory_class_path = getattr(
        settings, "BASEAPP_AUTH_USER_FACTORY", "apps.users.tests.factories.UserFactory"
    )
    module_path = ".".join(factory_class_path.split(".")[:-1])
    module = importlib.import_module(module_path)
    return getattr(module, factory_class_path.split(".")[-1])
