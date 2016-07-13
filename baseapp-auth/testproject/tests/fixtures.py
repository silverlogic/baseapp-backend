from io import BytesIO

from django.core import mail
from django.core.files.images import ImageFile

import pytest
from rest_framework.test import APIClient

import tests.factories as f


class Client(APIClient):
    def force_authenticate(self, user):
        self.user = user
        super().force_authenticate(user)


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def outbox():
    return mail.outbox


@pytest.fixture
def user_client():
    user = f.UserFactory()
    client = Client()
    client.force_authenticate(user)
    return client


@pytest.fixture
def image_base64():
    return 'iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAARVBMVEXPACr///8HAAIVAARnND5oABVzABcnCA6mACJHAA62ACXhztGcbXfi0dVzP0qZAB86EhqLWWPNsLZUABEjAAcaBAhbKjRAQ1vHAAAA+0lEQVQokYWTCZKEIAxFw2cTV9z6/kftsMjoiG2qVPQlAZMfEod1vfI7sHvVd+Uj5ecyWhSz43LFM0Pp9NS2k3aSHeYTHhSw6YayNZod1HDg4QO4AqPDCnyGjDnW0D/jBCrhuUKZA3PAi8V6p0Qr7MJ4hGxquNkwCuosdI2G9Laj/iGYwyV6UnC8FFeSXh0U+Zi7ig087Zgoli7eiY4m8GqCJKDN7ukSf9EtcMZHjjOOyUt03jktQ3KfKpr3FuUA+Wjpx6oWfuylLC9F5ZZsP1ry1tAHOZgshyAmeeOmiClKcX2W4l3I21nIZQxMGANzG4PXIcojyHHyMoJf+KcJUmsQs8MAAAAASUVORK5CYII='


@pytest.fixture
def image_djangofile(image_base64):
    i = BytesIO(image_base64.encode('utf-8'))
    return ImageFile(i, name='image.png')
