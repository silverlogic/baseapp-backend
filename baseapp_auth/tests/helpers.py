import importlib
import json
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:
    from factory.django import DjangoModelFactory

from baseapp_core.tests.helpers import (  # noqa: F401
    responseBadRequest,
    responseCreated,
    responseEquals,
    responseForbidden,
    responseMethodNotAllowed,
    responseNoContent,
    responseNotFound,
    responseOk,
    responseUnauthorized,
)


def get_json(data) -> Any:
    return json.loads(json.dumps(data))


def get_user_factory() -> "type[DjangoModelFactory]":
    factory_class_path = getattr(
        settings, "BASEAPP_AUTH_USER_FACTORY", "apps.users.tests.factories.UserFactory"
    )
    module_path = ".".join(factory_class_path.split(".")[:-1])
    module = importlib.import_module(module_path)
    return getattr(module, factory_class_path.split(".")[-1])
