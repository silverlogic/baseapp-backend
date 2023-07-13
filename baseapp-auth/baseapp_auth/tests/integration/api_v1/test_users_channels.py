# import pytest
# from channels.testing import WebsocketCommunicator

# from apps.asgi import application

# pytestmark = pytest.mark.django_db


# class TestUsersChannels:
#     @pytest.fixture(scope="function")
#     @pytest.mark.asyncio
#     async def test_user_can_connect(self, async_user_client):
#         communicator = WebsocketCommunicator(
#             application, "/ws/users/", subprotocols=["Authorization", async_user_client.token.key]
#         )
#         connected, subprotocol = await communicator.connect()
#         assert connected
#         message = await communicator.receive_json_from()
#         assert message["type"] == "websocket_accept"
#         await communicator.disconnect()

#     @pytest.fixture(scope="function")
#     @pytest.mark.asyncio
#     async def test_anon_cant_connect(self):
#         communicator = WebsocketCommunicator(
#             application, "/ws/users/", subprotocols=["Authorization", ""]
#         )
#         connected, subprotocol = await communicator.connect()
#         assert not connected
#         await communicator.disconnect()
