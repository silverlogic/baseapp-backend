from unittest.mock import patch

from baseapp.activity_log.graphql.subscriptions import OnNewActivityLogMessage


def test_new_message_broadcasts_to_room() -> None:
    with patch.object(OnNewActivityLogMessage, "broadcast") as mock_broadcast:
        OnNewActivityLogMessage.new_message(message="hello", room_id="room-42")

    mock_broadcast.assert_called_once_with(group="room-42", payload={"message": "hello"})
