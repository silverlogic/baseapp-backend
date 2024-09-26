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

Profile = swapper.load_model("baseapp_profiles", "Profile")
ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Message = swapper.load_model("baseapp_chats", "Message")


class ChatRoomParticipantObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node,)
        model = ChatRoomParticipant
        fields = ("id", "profile")
        filter_fields = ("profile__target_content_type",)


VerbsEnum = graphene.Enum.from_enum(Message.Verbs)


class MessageObjectType(DjangoObjectType):
    action_object = graphene.Field(relay.Node)
    verb = graphene.Field(VerbsEnum)
    content = graphene.String(required=False)

    class Meta:
        interfaces = (relay.Node,)
        model = Message
        fields = (
            "id",
            "verb",
            "content",
            "user",
            "profile",
            "created",
            "room",
            "action_object",
            "extra_data",
            "in_reply_to",
        )
        filter_fields = ("verb",)

    @classmethod
    def get_node(cls, info, id):
        try:
            message = cls._meta.model.objects.get(id=id)
            if not info.context.user.has_perm("baseapp_chats.view_message", message):
                return None
            return message
        except cls._meta.model.DoesNotExist:
            return None


class ChatRoomObjectType(DjangoObjectType):
    all_messages = DjangoFilterConnectionField(get_object_type_for_model(Message))
    participants = DjangoConnectionField(get_object_type_for_model(ChatRoomParticipant))
    unread_messages_count = graphene.Int(profile_id=graphene.ID(required=False))

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

    def resolve_unread_messages_count(self, info, profile_id=None, **kwargs):
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=profile_pk, user=info.context.user)
            if not profile:
                return None
        else:
            profile_pk = info.context.user.current_profile.pk

        unread_messages = UnreadMessageCount.objects.filter(
            room=self,
            profile_id=profile_pk,
        ).first()

        return unread_messages.count if unread_messages else 0

    class Meta:
        interfaces = (relay.Node,)
        model = ChatRoom
        fields = ("id", "last_message_time", "last_message", "participants", "name", "image")
        filterset_class = ChatRoomFilter
