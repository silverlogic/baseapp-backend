from collections.abc import Iterable

import strawberry
import swapper
from django.db.models import Model, Q, Sum
from strawberry.types import Info
from strawberry_django.resolvers import django_resolver

from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import CountedConnection, Node, type_for_model
from baseapp_core.strawberry.connections import connection

from ..filters import ChatRoomFilter

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")


@strawberry.interface(name="ChatRoomsInterface")
class ChatRoomsInterface(Node):
    @connection(CountedConnection[type_for_model(ChatRoom)] | None, filterset_class=ChatRoomFilter)
    def chat_rooms(self, info: Info) -> Iterable[Model]:
        if not info.context.user.has_perm("baseapp_chats.list_chatrooms", self):
            return ChatRoom.objects.none()

        qs = ChatRoom.objects.filter(participants__profile_id=self.pk).order_by(
            "-last_message_time", "-created"
        )

        # Exclude rooms with a participant blocked by / blocking self (when blocks is installed).
        if blocks_service := shared_services.get("blocks.lookup"):
            qs = qs.exclude(
                participants__profile_id__in=blocks_service.get_blocked_profile_ids(self.pk)
            )
            qs = qs.exclude(
                participants__profile_id__in=blocks_service.get_blocker_profile_ids(self.pk)
            )

        # Recipients only see 1-on-1 rooms they didn't create once they have a message.
        return qs.exclude(
            Q(is_group=False)
            & Q(created_by_profile__isnull=False)
            & ~Q(created_by_profile_id=self.pk)
            & Q(last_message__isnull=True)
        )

    @strawberry.field
    @django_resolver(qs_hook=None)  # async-safe in subscription payloads
    def unread_messages_count(self, info: Info) -> int | None:
        if not info.context.user.has_perm("baseapp_chats.list_chatrooms", self):
            return None
        result = UnreadMessageCount.objects.filter(profile_id=self.pk).aggregate(
            total_count=Sum("count")
        )
        return result["total_count"] or 0
