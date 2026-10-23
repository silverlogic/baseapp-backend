"""
Sessions over BaseApp's GraphQL WebSocket consumer, which authenticates from the
`connection_init` payload (as baseapp-frontend sends it) and never runs
`GRAPHENE["MIDDLEWARE"]`.
"""

import textwrap

import channels.routing
import channels_graphql_ws.testing
import pytest
import swapper
from channels.db import database_sync_to_async
from channels_graphql_ws.client import GraphqlWsResponseError
from django.urls import path

from baseapp_chats.tests.factories import ChatRoomFactory, ChatRoomParticipantFactory
from baseapp_chats.utils import send_message
from baseapp_core.authentication import authenticate_jwt
from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer
from baseapp_core.tests.factories import UserFactory

from ...graphql.middleware import ImpersonationWebsocketGraphqlMiddleware
from ...models import ImpersonationAction
from ...services import end_impersonation

Message = swapper.load_model("baseapp_chats", "Message")

pytestmark = pytest.mark.django_db(transaction=True)

ME = "query Me { me { id impersonation { id } } }"
DELETE_NODE = """
    mutation DeleteSomething($input: DeleteNodeInput!) {
        deleteNode(input: $input) { deletedID }
    }
"""
ROOM_UPDATES = """
    subscription RoomUpdates($profileId: ID!) {
      chatRoomOnRoomUpdate(profileId: $profileId) {
        room { node { id lastMessage { content } } }
      }
    }
"""
MESSAGES_COUNT = """
    subscription MessagesCount($profileId: ID!) {
      chatRoomOnMessagesCountUpdate(profileId: $profileId) {
        profile { id }
      }
    }
"""
HIDE_CHATS = [
    "baseapp_chats.list_chatrooms",
    "baseapp_chats.view_chatroom",
    "baseapp_chats.view_message",
]


@pytest.fixture
def ws_connect():
    """Connects to `GraphqlWsJWTAuthenticatedConsumer` with a session's tokens."""
    clients = []

    async def connect(tokens: dict) -> channels_graphql_ws.testing.GraphqlWsClient:
        application = channels.routing.ProtocolTypeRouter(
            {
                "websocket": channels.routing.URLRouter(
                    [path("graphql/", GraphqlWsJWTAuthenticatedConsumer.as_asgi())]
                )
            }
        )
        transport = channels_graphql_ws.testing.GraphqlWsTransport(
            application=application, path="graphql/"
        )
        client = channels_graphql_ws.testing.GraphqlWsClient(transport)
        clients.append(client)
        await client.connect_and_init(
            payload={"Authorization": tokens["access"], "Refresh": tokens["refresh"]}
        )
        return client

    yield connect

    for client in clients:
        assert not client.connected, "Test left a WebSocket client connected"


async def run(client, query: str, variables: dict | None = None) -> dict:
    """Run a query or mutation and return its payload, errors included."""
    msg_id = await client.send(
        msg_type="subscribe",
        payload={"query": textwrap.dedent(query), "variables": variables or {}},
    )
    try:
        payload = await client.receive(wait_id=msg_id)
    except GraphqlWsResponseError as exc:
        payload = exc.response["payload"]
    await client.receive(wait_id=msg_id)  # complete
    return payload


async def subscribe(client, query: str, variables: dict) -> str:
    return await client.send(
        msg_type="subscribe",
        payload={"query": textwrap.dedent(query), "variables": variables},
    )


def error_code(payload: dict) -> str | None:
    return payload["errors"][0].get("extensions", {}).get("code")


async def relay_id(obj) -> str:
    return await database_sync_to_async(lambda: obj.relay_id)()


class TestAuthentication:
    def test_core_authentication_attaches_the_session(self, member, start_session) -> None:
        session, tokens = start_session()
        user, new_access = authenticate_jwt(tokens["access"], tokens["refresh"])
        assert user == member
        assert user.impersonation == session
        assert new_access is None

    def test_core_authentication_refuses_ended_sessions(self, start_session) -> None:
        session, tokens = start_session()
        end_impersonation(session)
        assert authenticate_jwt(tokens["access"], tokens["refresh"]) == (None, None)
        # Nor does the refresh token mint a new access token.
        assert authenticate_jwt("garbage", tokens["refresh"]) == (None, None)

    def test_consumer_runs_the_websocket_middleware(self) -> None:
        consumer = GraphqlWsJWTAuthenticatedConsumer()
        assert any(
            isinstance(middleware, ImpersonationWebsocketGraphqlMiddleware)
            for middleware in consumer.middleware
        )

    @pytest.mark.asyncio
    async def test_queries_run_as_the_target(self, member, ws_connect, start_session) -> None:
        session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        payload = await run(client, ME)
        await client.finalize()
        assert payload["data"]["me"]["id"] == await relay_id(member)
        assert payload["data"]["me"]["impersonation"]["id"] == await relay_id(session)

    @pytest.mark.asyncio
    async def test_ended_session_cannot_connect(self, ws_connect, start_session) -> None:
        session, tokens = await database_sync_to_async(start_session)()
        await database_sync_to_async(end_impersonation)(session)
        client = await ws_connect(tokens)
        payload = await run(client, ME)
        await client.finalize()
        assert payload["data"]["me"] is None

    @pytest.mark.asyncio
    async def test_session_ended_after_connecting_stops_working(
        self, ws_connect, start_session
    ) -> None:
        session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        await database_sync_to_async(end_impersonation)(session)
        payload = await run(client, ME)
        await client.finalize()
        assert error_code(payload) == "impersonation_ended"


class TestMutations:
    @pytest.mark.asyncio
    async def test_read_only_sessions_refuse_mutations(self, ws_connect, start_session) -> None:
        session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        payload = await run(client, DELETE_NODE, {"input": {"id": "x"}})
        await client.finalize()
        assert error_code(payload) == "impersonation_read_only"
        assert not await ImpersonationAction.objects.filter(session=session).aexists()

    @pytest.mark.asyncio
    async def test_act_as_mutations_are_recorded(self, settings, ws_connect, start_session) -> None:
        settings.BASEAPP_AUTH_IMPERSONATION_READ_ONLY = False
        session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        payload = await run(client, DELETE_NODE, {"input": {"id": "x"}})
        await client.finalize()
        # The mutation ran as the target and failed (no such node).
        assert error_code(payload) != "impersonation_read_only"
        action = await ImpersonationAction.objects.aget(session=session)
        assert (action.method, action.path, action.operation_name, action.succeeded) == (
            "WS",
            "graphql/",  # the test transport's path
            "deleteNode",
            False,
        )

    @pytest.mark.asyncio
    async def test_denylisted_mutations_are_refused(
        self, settings, ws_connect, start_session
    ) -> None:
        settings.BASEAPP_AUTH_IMPERSONATION_READ_ONLY = False
        settings.BASEAPP_AUTH_IMPERSONATION_DENYLIST = ["deleteNode"]
        session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        payload = await run(client, DELETE_NODE, {"input": {"id": "x"}})
        await client.finalize()
        assert error_code(payload) == "impersonation_forbidden"
        assert not await ImpersonationAction.objects.filter(session=session).aexists()


class TestHiddenChats:
    @pytest.fixture
    def target_room(self, member):
        """A room of the target's with another user, who sends the messages."""
        other = UserFactory()
        room = ChatRoomFactory(created_by=other)
        ChatRoomParticipantFactory(room=room, profile=member.profile)
        ChatRoomParticipantFactory(room=room, profile=other.profile)
        return room, other

    @staticmethod
    def send(room, other) -> None:
        send_message(
            room=room,
            profile=other.profile,
            user=other,
            content="Private",
            verb=Message.Verbs.SENT_MESSAGE,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", [ROOM_UPDATES, MESSAGES_COUNT])
    async def test_room_subscriptions_are_hidden(
        self, settings, member, target_room, ws_connect, start_session, query
    ) -> None:
        settings.BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS = HIDE_CHATS
        room, other = target_room
        _session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        await subscribe(client, query, {"profileId": await relay_id(member.profile)})
        await client.assert_no_messages()

        await database_sync_to_async(self.send)(room, other)

        await client.assert_no_messages()
        await client.finalize()

    @pytest.mark.asyncio
    async def test_room_subscriptions_work_without_the_denial(
        self, member, target_room, ws_connect, start_session
    ) -> None:
        room, other = target_room
        _session, tokens = await database_sync_to_async(start_session)()
        client = await ws_connect(tokens)
        sub_id = await subscribe(
            client, ROOM_UPDATES, {"profileId": await relay_id(member.profile)}
        )
        await client.assert_no_messages()

        await database_sync_to_async(self.send)(room, other)

        response = await client.receive(assert_id=sub_id, assert_type="next")
        await client.finalize()
        node = response["data"]["chatRoomOnRoomUpdate"]["room"]["node"]
        assert node["lastMessage"]["content"] == "Private"
