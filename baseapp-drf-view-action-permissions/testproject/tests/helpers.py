import pytest
from rest_framework import status


def responseEquals(response, status_code):
    __tracebackhide__ = True
    assert isinstance(
        response.data, (dict, list)
    ), "Response must include at least an empty object or else IOS will go crazy."
    if response.status_code != status_code:
        pytest.fail(
            "Wrong status code. Got {}, expected {}".format(
                response.status_code, status_code
            )
        )


def responseOk(response):
    responseEquals(response, status.HTTP_200_OK)


def responseCreated(response):
    responseEquals(response, status.HTTP_201_CREATED)


def responseForbidden(response):
    responseEquals(response, status.HTTP_403_FORBIDDEN)


def responseNoContent(response):
    responseEquals(response, status.HTTP_204_NO_CONTENT)
