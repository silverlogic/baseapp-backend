import importlib
import json

import pytest
from django.conf import settings
from rest_framework import status

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


def allauthResponseEquals(response, status_code):
    __tracebackhide__ = True
    try:
        response_data = response.json()
    except (AttributeError, ValueError, TypeError):
        response_data = None
    assert isinstance(
        response_data, (dict, list)
    ), "Response must include at least an empty object or else IOS will go crazy."
    if response.status_code != status_code:
        pytest.fail(
            "Wrong status code. Got {}, expected {}".format(response.status_code, status_code)
        )


def allauthResponseOk(response):
    allauthResponseEquals(response, status.HTTP_200_OK)


def allauthResponseCreated(response):
    allauthResponseEquals(response, status.HTTP_201_CREATED)


def allauthResponseBadRequest(response):
    allauthResponseEquals(response, status.HTTP_400_BAD_REQUEST)


def allauthResponseUnauthorized(response):
    allauthResponseEquals(response, status.HTTP_401_UNAUTHORIZED)


def allauthResponseNoContent(response):
    allauthResponseEquals(response, status.HTTP_204_NO_CONTENT)


def allauthResponseForbidden(response):
    allauthResponseEquals(response, status.HTTP_403_FORBIDDEN)


def allauthResponseNotFound(response):
    allauthResponseEquals(response, status.HTTP_404_NOT_FOUND)


def allauthResponseMethodNotAllowed(response):
    allauthResponseEquals(response, status.HTTP_405_METHOD_NOT_ALLOWED)
