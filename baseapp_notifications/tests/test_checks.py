import pytest

from baseapp_notifications.checks import check_email_sender


def test_default_email_sender_passes() -> None:
    assert check_email_sender() == []


@pytest.mark.parametrize(
    "path, error_id",
    [
        ("baseapp_notifications.utils.no_such_sender", "baseapp_notifications.E001"),
        ("no_such_module.send", "baseapp_notifications.E001"),
        ("baseapp_notifications.services.DEFAULT_EMAIL_SENDER", "baseapp_notifications.E002"),
    ],
)
def test_invalid_email_sender_is_reported(settings, path, error_id) -> None:
    settings.BASEAPP_NOTIFICATIONS_EMAIL_SENDER = path

    [error] = check_email_sender()

    assert error.id == error_id
