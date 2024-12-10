import graphene
import swapper
from baseapp_core.graphql import (
    DjangoObjectType,
    ThumbnailField,
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


class BaseChatRoomParticipantObjectType:
    class Meta:
        interfaces = (relay.Node,)
        model = ChatRoomParticipant
        fields = ("id", "has_archived_room", "profile")
        filter_fields = ("profile__target_content_type",)


class ChatRoomParticipantObjectType(BaseChatRoomParticipantObjectType, DjangoObjectType):
    class Meta(BaseChatRoomParticipantObjectType.Meta):
        pass


VerbsEnum = graphene.Enum.from_enum(Message.Verbs)


class BaseMessageObjectType:
    action_object = graphene.Field(relay.Node)
    verb = graphene.Field(VerbsEnum)
    content = graphene.String(required=False)
    is_read = graphene.Boolean(profile_id=graphene.ID(required=False))

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
            "is_read",
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

    def resolve_is_read(self, info, profile_id=None, **kwargs):
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=profile_pk, user=info.context.user)
            if not profile:
                return None
        else:
            profile_pk = (
                info.context.user.current_profile
                if hasattr(info.context.user, "current_profile")
                and hasattr(info.context.user.current_profile, "pk")
                else (
                    info.context.user.profile.pk
                    if hasattr(info.context.user, "profile")
                    and hasattr(info.context.user.profile, "pk")
                    else None
                )
            )

        message_status = self.statuses.filter(profile_id=profile_pk).first()

        return message_status and message_status.is_read


class MessageObjectType(BaseMessageObjectType, DjangoObjectType):
    class Meta(BaseMessageObjectType.Meta):
        pass


class BaseChatRoomObjectType:
    all_messages = DjangoFilterConnectionField(get_object_type_for_model(Message))
    participants = DjangoConnectionField(get_object_type_for_model(ChatRoomParticipant))
    unread_messages = graphene.Field(
        get_object_type_for_model(UnreadMessageCount), profile_id=graphene.ID(required=False)
    )
    image = ThumbnailField(required=False)
    is_archived = graphene.Boolean(profile_id=graphene.ID(required=False))

    @classmethod
    def get_node(cls, info, id):
        try:
            room = cls._meta.model.objects.get(id=id)
            if not info.context.user.has_perm("baseapp_chats.view_chatroom", room):
                return None
            return room

        except cls._meta.model.DoesNotExist:
            return None

    def resolve_all_messages(self, info, **kwargs):
        return self.messages.all().order_by("-created")

    def resolve_is_archived(self, info, profile_id=None, **kwargs):
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=profile_pk, user=info.context.user)
            if not profile:
                return None
        else:
            profile_pk = (
                info.context.user.current_profile.pk
                if hasattr(info.context.user, "current_profile")
                and hasattr(info.context.user.current_profile, "pk")
                else (
                    info.context.user.profile.pk
                    if hasattr(info.context.user, "profile")
                    and hasattr(info.context.user.profile, "pk")
                    else None
                )
            )
        return self.participants.filter(profile_id=profile_pk, has_archived_room=True).exists()

    def resolve_unread_messages(self, info, profile_id=None, **kwargs):
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=profile_pk, user=info.context.user)
            if not profile:
                return None
        else:
            profile_pk = (
                info.context.user.current_profile
                if hasattr(info.context.user, "current_profile")
                and hasattr(info.context.user.current_profile, "pk")
                else (
                    info.context.user.profile.pk
                    if hasattr(info.context.user, "profile")
                    and hasattr(info.context.user.profile, "pk")
                    else None
                )
            )

        unread_messages = UnreadMessageCount.objects.filter(
            room=self,
            profile_id=profile_pk,
        ).first()

        return unread_messages

    class Meta:
        interfaces = (relay.Node,)
        model = ChatRoom
        fields = (
            "id",
            "last_message_time",
            "last_message",
            "participants",
            "title",
            "image",
            "is_group",
        )
        filterset_class = ChatRoomFilter


class ChatRoomObjectType(BaseChatRoomObjectType, DjangoObjectType):
    class Meta(BaseChatRoomObjectType.Meta):
        pass


class BaseUnreadMessageObjectType:
    class Meta:
        interfaces = (relay.Node,)
        model = UnreadMessageCount
        fields = ("count", "marked_unread")


class UnreadMessageObjectType(BaseUnreadMessageObjectType, DjangoObjectType):
    class Meta(BaseUnreadMessageObjectType.Meta):
        pass
