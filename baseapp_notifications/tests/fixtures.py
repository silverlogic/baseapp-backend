from collections.abc import Callable
from typing import Any

import pytest

from baseapp_core.plugins import shared_services


@pytest.fixture
def send_notification() -> Callable[..., Any]:
    """
    Fixture that returns the send_notification method from the notifications service.
    """
    service = shared_services.get("notifications")
    return service.send_notification


@pytest.fixture
def notification_groups_registry() -> Any:
    """An empty notification-group registry, restored to its previous content afterwards."""
    from baseapp_notifications.groups import notification_groups

    saved = dict(notification_groups._groups)
    notification_groups.clear()
    yield notification_groups
    notification_groups.clear()
    notification_groups._groups.update(saved)
