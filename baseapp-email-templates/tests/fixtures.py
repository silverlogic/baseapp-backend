import pytest


@pytest.fixture
def outbox(mailoutbox):
    return mailoutbox
