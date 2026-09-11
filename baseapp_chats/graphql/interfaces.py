from typing import TYPE_CHECKING

import graphene
import swapper
from django.db.models import Q, Sum
from query_optimizer import DjangoConnectionField

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model
from baseapp_core.plugins import shared_services

if TYPE_CHECKING:
    from django.db.models import QuerySet

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")


class ChatRoomsInterface(RelayNode):
    chat_rooms = DjangoConnectionField(get_object_type_for_model(ChatRoom))
    unread_messages_count = graphene.Int()

    def resolve_chat_rooms(self, info, **kwargs) -> "QuerySet":
        if not info.context.user.has_perm("baseapp_chats.list_chatrooms", self):
            return ChatRoom.objects.none()

        qs = ChatRoom.objects.filter(
            participants__profile_id=self.pk,
        ).order_by("-last_message_time", "-created")

        # Exclude rooms involving profiles blocked by / blocking self, via the
        # optional blocks.lookup service. When baseapp_blocks isn't installed
        # there are no blocks, so nothing is excluded here.
        if blocks_service := shared_services.get("blocks.lookup"):
            # Rooms with a participant that self blocks.
            qs = qs.exclude(
                participants__profile_id__in=blocks_service.get_blocked_profile_ids(self.pk)
            )
            # Rooms with a participant that blocks self.
            qs = qs.exclude(
                participants__profile_id__in=blocks_service.get_blocker_profile_ids(self.pk)
            )

        # Exclude empty 1-on-1 chat rooms where current profile is not the creator
        # Recipients should only see 1-on-1 chats if they have at least one message
        qs = qs.exclude(
            Q(is_group=False)
            & Q(created_by_profile__isnull=False)
            & ~Q(created_by_profile_id=self.pk)
            & Q(last_message__isnull=True)
        )

        return qs

    def resolve_unread_messages_count(self, info, **kwargs) -> int | None:
        if not info.context.user.has_perm("baseapp_chats.list_chatrooms", self):
            return None

        aggregate_result = UnreadMessageCount.objects.filter(
            profile_id=self.pk,
        ).aggregate(total_count=Sum("count"))

        return aggregate_result["total_count"] or 0
