import pytest
from rest_framework import status


def responseEquals(response, status_code) -> None:
    __tracebackhide__ = True
    assert isinstance(
        response.data, (dict, list)
    ), "Response must include at least an empty object or else IOS will go crazy."
    if response.status_code != status_code:
        pytest.fail(
            "Wrong status code. Got {}, expected {}".format(response.status_code, status_code)
        )


def responseOk(response) -> None:
    responseEquals(response, status.HTTP_200_OK)


def responseCreated(response) -> None:
    responseEquals(response, status.HTTP_201_CREATED)


def responseBadRequest(response) -> None:
    responseEquals(response, status.HTTP_400_BAD_REQUEST)


def responseUnauthorized(response) -> None:
    responseEquals(response, status.HTTP_401_UNAUTHORIZED)


def responseNoContent(response) -> None:
    responseEquals(response, status.HTTP_204_NO_CONTENT)


def responseForbidden(response) -> None:
    responseEquals(response, status.HTTP_403_FORBIDDEN)


def responseNotFound(response) -> None:
    responseEquals(response, status.HTTP_404_NOT_FOUND)


def responseMethodNotAllowed(response) -> None:
    responseEquals(response, status.HTTP_405_METHOD_NOT_ALLOWED)
