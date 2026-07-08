import pytest

from baseapp_core.plugins import shared_services


@pytest.fixture
def send_notification():
    """
    Fixture that returns the send_notification method from the notifications service.
    """
    service = shared_services.get("notifications")
    return service.send_notification
