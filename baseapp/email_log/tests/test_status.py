import pytest
from djmail.models import Message

from baseapp.email_log.status import (
    EmailLogStatus,
    djmail_statuses_for,
    status_from_djmail,
    status_to_djmail,
)


@pytest.mark.parametrize(
    "djmail_status, status",
    [
        (Message.STATUS_DRAFT, "queued"),
        (Message.STATUS_PENDING, "queued"),
        (Message.STATUS_SENT, "sent"),
        (Message.STATUS_FAILED, "failed"),
        (Message.STATUS_DISCARDED, "discarded"),
    ],
)
def test_status_from_djmail(djmail_status: int, status: str) -> None:
    assert status_from_djmail(djmail_status) == status


@pytest.mark.parametrize(
    "status, djmail_status",
    [
        ("queued", Message.STATUS_DRAFT),
        ("sending", Message.STATUS_DRAFT),
        ("sent", Message.STATUS_SENT),
        ("failed", Message.STATUS_FAILED),
        ("discarded", Message.STATUS_DISCARDED),
    ],
)
def test_status_to_djmail(status: str, djmail_status: int) -> None:
    assert status_to_djmail(status) == djmail_status


def test_every_status_round_trips_except_in_flight() -> None:
    for status in EmailLogStatus:
        if status == EmailLogStatus.SENDING:
            continue
        assert status_from_djmail(status_to_djmail(status)) == status


def test_djmail_statuses_for() -> None:
    assert sorted(djmail_statuses_for("queued")) == [Message.STATUS_DRAFT, Message.STATUS_PENDING]
    assert djmail_statuses_for("sending") == []
    assert djmail_statuses_for("failed") == [Message.STATUS_FAILED]


def test_unknown_statuses_raise() -> None:
    with pytest.raises(ValueError):
        status_from_djmail(99)
    with pytest.raises(ValueError):
        status_to_djmail("bounced")
