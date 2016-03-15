from django.core import mail

import pytest


@pytest.fixture
def outbox():
    return mail.outbox
