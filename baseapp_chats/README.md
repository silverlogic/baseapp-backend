# BaseApp Chats

Reusable app for one-to-one and group chat: rooms, messages, message statuses (read/unread receipts), and unread-message counts. Built on Django Channels for real-time delivery and pgtrigger for trigger-based denormalised counters.

## How to install

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

1. **Enable GraphQL websockets** in your project ([guide](../baseapp-core/baseapp_core/graphql/README.md#enable-websockets)). Chats relies on `channels_graphql_ws` for the message / room / unread-count subscriptions.

2. Add `baseapp_chats` to `INSTALLED_APPS` and run `./manage.py migrate`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_chats",
    # ...
]
```

3. Wire the auth backend slot:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_chats"),
    # ...
]
```

4. Make sure your project's `graphql.py` composes the schema via `plugin_registry.get_all_graphql_*()` so `ChatsQueries / ChatsMutations / ChatsSubscriptions` are picked up automatically.

5. Point the swapper settings at your concrete models (see [models](#models)):

```python
BASEAPP_CHATS_CHATROOM_MODEL = "chats.ChatRoom"
BASEAPP_CHATS_CHATROOMPARTICIPANT_MODEL = "chats.ChatRoomParticipant"
BASEAPP_CHATS_UNREADMESSAGECOUNT_MODEL = "chats.UnreadMessageCount"
BASEAPP_CHATS_MESSAGE_MODEL = "chats.Message"
BASEAPP_CHATS_MESSAGESTATUS_MODEL = "chats.MessageStatus"
```

## Models

All five models are abstract + swappable. Subclass the abstracts in a project-local app to add fields or behaviour; otherwise inherit the abstracts directly and only override `Meta`.

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `AbstractBaseChatRoom` | `ChatRoom` | Conversation between 2+ participants; carries `last_message`, denormalised `participants_count` / `messages_count`. |
| `AbstractChatRoomParticipant` | `ChatRoomParticipant` | Profile↔Room join row; role (member / admin), accepted-at, archived flag. |
| `AbstractBaseMessage` | `Message` | A single message. Supports replies via `in_reply_to`, system-generated messages, and a `GenericForeignKey` action object. |
| `AbstractMessageStatus` | `MessageStatus` | Per-participant read/unread receipt for a message. |
| `AbstractUnreadMessageCount` | `UnreadMessageCount` | Per-participant rolling counter; powers room-level "unread" badges. |

All five inherit `DocumentIdMixin`, so any chat object can be the target of mentions, comments, follows, etc. without extra wiring.

### Triggers

The concrete models attach four `pgtrigger` triggers (see [`baseapp_chats/triggers.py`](triggers.py)):

- `set_last_message_on_insert_trigger` — keeps `ChatRoom.last_message` / `last_message_time` current on insert.
- `update_last_message_on_delete_trigger` — recomputes `ChatRoom.last_message` when the current last message is deleted.
- `create_message_status_trigger` — creates a `MessageStatus` row per active participant when a `Message` is inserted.
- `increment_unread_count_trigger` / `decrement_unread_count_trigger` — keep `UnreadMessageCount.count` in sync as message statuses flip `is_read`.

Override these in your concrete `Meta.triggers` only when your model needs different counting semantics.

## GraphQL

### Queries

| Field | Description |
|---|---|
| `chatRoom(id)` | RelayNode fetch by relay id. Permission: `baseapp_chats.view_chatroom`. |

### Mutations

| Field | Purpose |
|---|---|
| `chatRoomCreate` | Create a 1-on-1 or group room. Dedupes 1-on-1 rooms. |
| `chatRoomUpdate` | Edit title / image, add or remove participants, hand off admin when the last admin leaves. |
| `chatRoomToggleAdmin` | Promote / demote a participant; refuses to demote the only remaining admin. |
| `chatRoomSendMessage` | Persist a message, fire the subscription, optionally persist mentions and trigger notifications. |
| `chatRoomEditMessage` | Edit message body and replace mentions. |
| `chatRoomDeleteMessage` | Soft-delete a message (sets `deleted=True`). |
| `chatRoomReadMessages` | Mark messages read; broadcasts `ChatRoomOnMessagesCountUpdate`. |
| `chatRoomUnread` | Flag a room as unread for a participant. |
| `chatRoomArchive` | Toggle the participant's archived flag for a room. |

### Subscriptions

| Field | Topic |
|---|---|
| `chatRoomOnMessage` | New / edited messages in a room. |
| `chatRoomOnRoomUpdate` | Room metadata, participant adds / removes. |
| `chatRoomOnMessagesCountUpdate` | Per-profile unread count changed. |

### Shared GraphQL interfaces

Chats publishes one shared interface via the registry — consuming object types opt in by name:

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class ProfileObjectType(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "ChatRoomsInterface")
        model = Profile
```

The interface exposes:

- `chatRooms` — paginated `ChatRoom` connection scoped to the profile.
- `unreadMessagesCount` — sum of `UnreadMessageCount.count` across all rooms the profile participates in.

## Shared services

### Provided

Chats registers one service via `apps.py.ready()`:

- **`chats_participation`** — `cleanup_user_participation(user)`. Removes the user's `ChatRoomParticipant` rows and recomputes affected rooms' `participants_count`. Called by the auth anonymize-user task. Consume it as:

  ```python
  from baseapp_core.plugins import shared_services

  if service := shared_services.get("chats_participation"):
      service.cleanup_user_participation(user)
  ```

### Consumed

Chats consumes the following services lazily via `shared_services.get(...)` — they are all optional, behaviour degrades gracefully when absent:

- `notifications` — push / email notification of new messages.
- `mentions` — persisting `@mention` references on `chatRoomSendMessage` / `chatRoomEditMessage`.

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-chats
```

The `-e` flag means any change you make in the cloned repo files will be reflected in the project. Run the test suite from the backend root:

```bash
docker compose run --rm web pytest baseapp_chats/
```
