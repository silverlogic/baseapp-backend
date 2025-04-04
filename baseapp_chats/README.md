# BaseApp Chats

This package provides a simple chat system for your project, where multiple profiles can chat with each other.

## Requirements:
```
- **baseapp-core** >= 0.3.7
- **baseapp-profile** >= 0.2.4
```

Run `pip install baseapp-chats`
And make sure to add the frozen version to your `requirements/base.txt` file

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_chats` to your project's `INSTALLED_APPS`

Make sure your Profile's GraphQL Object Types extends `ChatRoomsInterface` interface:

```python
from baseapp_chats.graphql.interfaces import ChatRoomsInterface

class ProfileObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, ChatRoomsInterface)
```

This is not necessary if you are using the `baseapp-profile` as it is without a custom ProfileObjectType implementation.

Expose `ChatsMutations`, `ChatsQueries` and `ChatsSubscriptions` in your GraphQL/graphene endpoint, like:

```python
from baseapp_chats.graphql.mutations import ChatsMutations
from baseapp_chats.graphql.queries import ChatsQueries
from baseapp_chats.graphql.subscriptions import ChatsSubscriptions


class Query(graphene.ObjectType, ChatsQueries):
    pass


class Mutation(graphene.ObjectType, ChatsMutations):
    pass


class Subscription(graphene.ObjectType, ChatsSubscriptions):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
```

Those will expose the following queries, mutations and subscriptions:

### Queries

- `chatRoom(id: ID!)`: Return a specific chatRoom

### Mutations

- `chatRoomCreate(profileId: ID!, participants: [ID!]!)`: Create a chatRoom with your profile and multiple participants
- `chatRoomSendMessage(roomId: ID!, profileId: ID!, content: String!, inReplyToId: ID)`: Send a message in a room, using a specific profile. Optionally, you can reply to a message by passing the `inReplyToId` argument.
- `chatRoomReadMessages(roomId: ID!, profileId: ID!, messageIds: [ID])`: Mark messages in a room as read by a specific profile, if `messageIds` is not passed, all messages will be marked as read.

### Subscriptions

- `chatRoomOnRoomUpdate(profileId: ID!)`: Subscribe to chat rooms updates under your current profile
- `chatRoomOnMessagesCountUpdate(profileId: ID!)`: Subscribe to unread/read messages count updates under your current profile
- `chatRoomOnMessage(roomId: ID!)`: Subscribe to new messages in a specific room

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-chats
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.