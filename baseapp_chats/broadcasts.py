"""Publishers for the chats subscriptions (`baseapp_chats.strawberry.subscriptions`).

Group names keep the original subscription class names, so subscribers listen on the same
channel groups.
"""

from collections.abc import Sequence

from django.db.models import Model

from baseapp_core.strawberry.subscriptions import broadcast, subscription_group


def room_updated(
    room: Model,
    removed_participants: Sequence[Model] = (),
    added_participants: Sequence[Model] = (),
) -> None:
    """Notify every participant (and every removed one) that `room` changed."""
    participant_ids = list(room.participants.values_list("profile_id", flat=True))
    removed_ids = [participant.profile.id for participant in removed_participants]
    payload = {
        "room": room,
        "removed_participants": list(removed_participants),
        "added_participants": list(added_participants),
    }
    for profile_pk in participant_ids + removed_ids:
        broadcast(subscription_group("ChatRoomOnRoomUpdate", str(profile_pk)), payload)


def new_message(message: Model, room_id: str) -> None:
    """Publish a new message to the room's subscribers and a room update to its participants."""
    edit_message(message, room_id)
    room_updated(message.room)


def edit_message(message: Model, room_id: str) -> None:
    broadcast(subscription_group("ChatRoomOnMessage", room_id), {"message": message})


def send_updated_chat_count(profile: Model, profile_id: str) -> None:
    broadcast(subscription_group("ChatRoomOnMessagesCountUpdate", profile_id), {"profile": profile})
