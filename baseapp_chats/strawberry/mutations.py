import strawberry
import swapper
from strawberry import UNSET
from strawberry.file_uploads import Upload

from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as g
from .types import ChatRoomLazyType, ChatRoomParticipantLazyType, MessageLazyType

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileLazyType = type_for_model(Profile)
IDList = list[strawberry.ID | None]


@strawberry.input(name="ChatRoomCreateInput")
class ChatRoomCreateInput(RelayMutationInput):
    profile_id: strawberry.ID
    participants: IDList
    is_group: bool | None = False
    title: str | None = UNSET


@strawberry.type(name="ChatRoomCreatePayload")
class ChatRoomCreatePayload(RelayMutationPayload):
    room: Edge[ChatRoomLazyType] | None = None
    profile: ProfileLazyType | None = None


@strawberry.input(name="ChatRoomUpdateInput")
class ChatRoomUpdateInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    title: str | None = UNSET
    image: Upload | None = UNSET
    delete_image: bool | None = False
    add_participants: IDList | None = strawberry.field(default_factory=list)
    remove_participants: IDList | None = strawberry.field(default_factory=list)


@strawberry.type(name="ChatRoomUpdatePayload")
class ChatRoomUpdatePayload(RelayMutationPayload):
    room: Edge[ChatRoomLazyType] | None = None
    removed_participants: list[ChatRoomParticipantLazyType | None] | None = None
    added_participants: list[ChatRoomParticipantLazyType | None] | None = None


@strawberry.input(name="ChatRoomsAddParticipantInput")
class ChatRoomsAddParticipantInput(RelayMutationInput):
    profile_id: strawberry.ID
    participant_profile_id: strawberry.ID
    room_ids: list[strawberry.ID]


@strawberry.type(name="ChatRoomsAddParticipantPayload")
class ChatRoomsAddParticipantPayload(RelayMutationPayload):
    rooms: list[ChatRoomLazyType | None] | None = None
    added_participants: list[ChatRoomParticipantLazyType | None] | None = None


@strawberry.input(name="ChatRoomSendMessageInput")
class ChatRoomSendMessageInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    content: str
    in_reply_to_id: strawberry.ID | None = UNSET
    mentioned_profile_ids: IDList | None = UNSET


@strawberry.type(name="ChatRoomSendMessagePayload")
class ChatRoomSendMessagePayload(RelayMutationPayload):
    message: Edge[MessageLazyType] | None = None


@strawberry.input(name="ChatRoomEditMessageInput")
class ChatRoomEditMessageInput(RelayMutationInput):
    id: strawberry.ID
    content: str
    mentioned_profile_ids: IDList | None = UNSET


@strawberry.type(name="ChatRoomEditMessagePayload")
class ChatRoomEditMessagePayload(RelayMutationPayload):
    message: Edge[MessageLazyType] | None = None


@strawberry.input(name="ChatRoomDeleteMessageInput")
class ChatRoomDeleteMessageInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="ChatRoomDeleteMessagePayload")
class ChatRoomDeleteMessagePayload(RelayMutationPayload):
    deleted_message: Edge[MessageLazyType] | None = None


@strawberry.input(name="ChatRoomReadMessagesInput")
class ChatRoomReadMessagesInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    message_ids: IDList | None = UNSET


@strawberry.type(name="ChatRoomReadMessagesPayload")
class ChatRoomReadMessagesPayload(RelayMutationPayload):
    room: ChatRoomLazyType | None = None
    profile: ProfileLazyType | None = None
    messages: list[MessageLazyType | None] | None = None


@strawberry.input(name="ChatRoomUnreadInput")
class ChatRoomUnreadInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID


@strawberry.type(name="ChatRoomUnreadPayload")
class ChatRoomUnreadPayload(RelayMutationPayload):
    room: ChatRoomLazyType | None = None
    profile: ProfileLazyType | None = None


@strawberry.input(name="ChatRoomArchiveInput")
class ChatRoomArchiveInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    archive: bool


@strawberry.type(name="ChatRoomArchivePayload")
class ChatRoomArchivePayload(RelayMutationPayload):
    room: ChatRoomLazyType | None = None


@strawberry.input(name="ChatRoomToggleAdminInput")
class ChatRoomToggleAdminInput(RelayMutationInput):
    target_participant_id: strawberry.ID
    profile_id: strawberry.ID
    room_id: strawberry.ID


@strawberry.type(name="ChatRoomToggleAdminPayload")
class ChatRoomToggleAdminPayload(RelayMutationPayload):
    participant: Edge[ChatRoomParticipantLazyType] | None = None


@strawberry.type
class ChatsMutations:
    chat_room_create = graphene_relay_mutation(
        g.ChatRoomCreate, ChatRoomCreateInput, ChatRoomCreatePayload
    )
    chat_room_update = graphene_relay_mutation(
        g.ChatRoomUpdate, ChatRoomUpdateInput, ChatRoomUpdatePayload
    )
    chat_rooms_add_participant = graphene_relay_mutation(
        g.ChatRoomsAddParticipant, ChatRoomsAddParticipantInput, ChatRoomsAddParticipantPayload
    )
    chat_room_send_message = graphene_relay_mutation(
        g.ChatRoomSendMessage, ChatRoomSendMessageInput, ChatRoomSendMessagePayload
    )
    chat_room_edit_message = graphene_relay_mutation(
        g.ChatRoomEditMessage, ChatRoomEditMessageInput, ChatRoomEditMessagePayload
    )
    chat_room_delete_message = graphene_relay_mutation(
        g.ChatRoomDeleteMessage, ChatRoomDeleteMessageInput, ChatRoomDeleteMessagePayload
    )
    chat_room_read_messages = graphene_relay_mutation(
        g.ChatRoomReadMessages, ChatRoomReadMessagesInput, ChatRoomReadMessagesPayload
    )
    chat_room_unread = graphene_relay_mutation(
        g.ChatRoomUnread, ChatRoomUnreadInput, ChatRoomUnreadPayload
    )
    chat_room_archive = graphene_relay_mutation(
        g.ChatRoomArchive, ChatRoomArchiveInput, ChatRoomArchivePayload
    )
    chat_room_toggle_admin = graphene_relay_mutation(
        g.ChatRoomToggleAdmin, ChatRoomToggleAdminInput, ChatRoomToggleAdminPayload
    )
