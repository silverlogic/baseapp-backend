from channels.generic.websocket import AsyncJsonWebsocketConsumer


class UsersConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if "user" in self.scope:
            user_id = self.scope["user"].id
            self.group_name = f"user-{user_id}-notifications"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept("Authorization")
            await self.send_json({"type": "websocket_accept"})
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
