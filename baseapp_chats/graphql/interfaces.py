import graphene
import swapper
from django.db.models import Q, Sum
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Block = swapper.load_model("baseapp_blocks", "Block")


class ChatRoomsInterface(RelayNode):
    chat_rooms = DjangoFilterConnectionField(get_object_type_for_model(ChatRoom))
    unread_messages_count = graphene.Int()

    def resolve_chat_rooms(self, info, **kwargs):
        if not info.context.user.has_perm("baseapp_chats.list_chatrooms", self):
            return ChatRoom.objects.none()

        qs = ChatRoom.objects.filter(
            participants__profile_id=self.pk,
        ).order_by("-last_message_time", "-created")

        # Exclude rooms with any blocked participant
        blocking_profile_ids = Block.objects.filter(actor_id=self.pk).values_list(
            "target_id", flat=True
        )
        qs = qs.exclude(participants__profile_id__in=blocking_profile_ids)

        # Exclude rooms with any participant that blocks the profile (self)
        blocker_profile_ids = Block.objects.filter(target_id=self.pk).values_list(
            "actor_id", flat=True
        )
        qs = qs.exclude(participants__profile_id__in=blocker_profile_ids)

        # Exclude empty 1-on-1 chat rooms where current profile is not the creator
        # Recipients should only see 1-on-1 chats if they have at least one message
        qs = qs.exclude(
            Q(is_group=False)
            & Q(created_by_profile__isnull=False)
            & ~Q(created_by_profile_id=self.pk)
            & Q(last_message__isnull=True)
        )

        return qs

    def resolve_unread_messages_count(self, info, **kwargs):
        if not info.context.user.has_perm("baseapp_chats.list_chatrooms", self):
            return None

        aggregate_result = UnreadMessageCount.objects.filter(
            profile_id=self.pk,
        ).aggregate(total_count=Sum("count"))

        return aggregate_result["total_count"] or 0
