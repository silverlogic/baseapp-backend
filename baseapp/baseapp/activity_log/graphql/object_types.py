import graphene
import swapper
from baseapp_core.graphql import (
    DjangoObjectType,
    get_object_type_for_model,
    get_pk_from_relay_id,
)
from graphene import relay
from graphene_django import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField

from .filters import ChatRoomFilter
from pghistory.models import MiddlewareEvents

Profile = swapper.load_model("baseapp_profiles", "Profile")
# ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
# ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
# UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
# Message = swapper.load_model("baseapp_chats", "Message")


class BaseActivityEventObjectType:
    # all_messages = DjangoFilterConnectionField(get_object_type_for_model(Message))
    # participants = DjangoConnectionField(get_object_type_for_model(ChatRoomParticipant))
    # unread_messages_count = graphene.Int(profile_id=graphene.ID(required=False))

    def resolve_all_messages(self, info, **kwargs):
        return self.messages.all().order_by("-created")

    @classmethod
    def get_node(cls, info, id):
        try:
            room = cls._meta.model.objects.get(id=id)
            if not info.context.user.has_perm("baseapp_chats.view_chatroom", room):
                return None
            return room

        except cls._meta.model.DoesNotExist:
            return None

    class Meta:
        interfaces = (relay.Node,)
        model = MiddlewareEvents
        fields = ("id", "pk", "user", "url", "pgh_diff", "pgh_created_at")
        # LISTA de campos:
        # pgh_slug = models.TextField(
        # primary_key=True, help_text="The unique identifier across all event tables."
        # )
        # pgh_model = models.CharField(max_length=64, help_text="The event model.")
        # pgh_id = models.BigIntegerField(help_text="The primary key of the event.")
        # pgh_created_at = models.DateTimeField(
        # auto_now_add=True, help_text="When the event was created."
        # )
        # pgh_label = models.TextField(help_text="The event label.")
        # pgh_data = utils.JSONField(help_text="The raw data of the event.")
        # pgh_diff = utils.JSONField(help_text="The diff between the previous event of the same label.")
        # pgh_context_id = models.UUIDField(null=True, help_text="The context UUID.")
        # pgh_context = utils.JSONField(
        # null=True,
        # help_text="The context associated with the event.",
        # )
        # pgh_obj_model = models.CharField(max_length=64, help_text="The object model.")
        # pgh_obj_id = models.TextField(null=True, help_text="The primary key of the object.")
        filterset_class = ChatRoomFilter


class ActivityEventObjectType(BaseActivityEventObjectType, DjangoObjectType):
    class Meta(BaseActivityEventObjectType.Meta):
        pass
