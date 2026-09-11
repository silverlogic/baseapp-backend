import base64
from collections.abc import AsyncGenerator, Generator
from io import BytesIO
from typing import Any

import pytest
import responses
from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from django.core.mail import EmailMessage
from django.test import AsyncClient as DjangoAsyncClient
from django.test import Client as DjClient
from rest_framework.test import APIClient

import baseapp_core.tests.factories as f

IMAGE_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAARVBMVEXPACr///8HAAIVAARnND5oABVzABcnCA6mACJHAA62ACXhztGcbXfi0dVzP0qZAB86EhqLWWPNsLZUABEjAAcaBAhbKjRAQ1vHAAAA+0lEQVQokYWTCZKEIAxFw2cTV9z6/kftsMjoiG2qVPQlAZMfEod1vfI7sHvVd+Uj5ecyWhSz43LFM0Pp9NS2k3aSHeYTHhSw6YayNZod1HDg4QO4AqPDCnyGjDnW0D/jBCrhuUKZA3PAi8V6p0Qr7MJ4hGxquNkwCuosdI2G9Laj/iGYwyV6UnC8FFeSXh0U+Zi7ig087Zgoli7eiY4m8GqCJKDN7ukSf9EtcMZHjjOOyUt03jktQ3KfKpr3FuUA+Wjpx6oWfuylLC9F5ZZsP1ry1tAHOZgshyAmeeOmiClKcX2W4l3I21nIZQxMGANzG4PXIcojyHHyMoJf+KcJUmsQs8MAAAAASUVORK5CYII="


class Client(APIClient):
    def force_authenticate(self, user) -> None:
        self.user = user
        super().force_authenticate(user)


class DjangoClient(DjClient):
    def force_login(self, user, backend=None) -> None:
        self.user = user
        super().force_login(user, backend=backend)


class AsyncClient(DjangoAsyncClient):
    def force_authenticate(self, user) -> None:
        self.user = user


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def django_client() -> DjangoClient:
    return DjangoClient()


@pytest.fixture
def outbox(mailoutbox) -> list[EmailMessage]:
    return mailoutbox


@pytest.fixture
def user_client() -> Client:
    user = f.UserFactory()
    client = Client()
    client.force_authenticate(user)
    return client


@pytest.fixture
def django_user_client() -> DjangoClient:
    user = f.UserFactory()
    client = DjangoClient()
    client.force_login(user)
    return client


@pytest.fixture
async def async_user_client() -> AsyncGenerator[AsyncClient, None]:
    user = await sync_to_async(f.UserFactory)()
    token = await sync_to_async(f.TokenFactory)(user=user)
    client = AsyncClient()
    client.force_authenticate(user)
    client.token = token
    yield client
    await sync_to_async(token.delete)()
    await sync_to_async(user.delete)()


@pytest.fixture(autouse=True)
def responses_mock() -> Generator[responses.RequestsMock, None, None]:
    with responses.RequestsMock() as r:
        yield r


@pytest.fixture
def image_base64() -> str:
    return IMAGE_BASE64


@pytest.fixture
def image_djangofile(image_base64) -> ImageFile:
    i = BytesIO(base64.b64decode(image_base64))
    return ImageFile(i, name="image.png")


@pytest.fixture
def corrupted_image() -> ContentFile:
    return ContentFile("corrupted", name="image.png")


@pytest.fixture
def deep_link_mock_success(responses_mock) -> None:
    responses_mock.add(
        responses.POST,
        "https://api.branch.io/v1/url",
        json={"url": "https://example.com/128z8x81"},
        status=200,
    )


@pytest.fixture
def deep_link_mock_error(responses_mock) -> None:
    responses_mock.add(responses.POST, "https://api.branch.io/v1/url", status=400)


@pytest.fixture(scope="session")
def celery_config() -> Any:
    from celery import Celery

    app = Celery("apps")
    return app.config_from_object("django.conf:settings", namespace="CELERY")
