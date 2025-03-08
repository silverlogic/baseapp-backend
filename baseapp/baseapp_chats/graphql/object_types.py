import graphene
import swapper
from django.db.models import Case, When
from graphene import relay
from graphene_django import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import (
    DjangoObjectType,
    ThumbnailField,
    get_object_type_for_model,
    get_pk_from_relay_id,
)

from .filters import ChatRoomFilter

Profile = swapper.load_model("baseapp_profiles", "Profile")
ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
ChatRoomParticipantRoleTypesEnum = graphene.Enum.from_enum(
    ChatRoomParticipant.ChatRoomParticipantRoles
)
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Message = swapper.load_model("baseapp_chats", "Message")


class BaseChatRoomParticipantObjectType:
    role = graphene.Field(ChatRoomParticipantRoleTypesEnum)

    class Meta:
        interfaces = (relay.Node,)
        model = ChatRoomParticipant
        fields = ("id", "has_archived_room", "profile", "role")
        filter_fields = ("profile__target_content_type",)


class ChatRoomParticipantObjectType(BaseChatRoomParticipantObjectType, DjangoObjectType):
    class Meta(BaseChatRoomParticipantObjectType.Meta):
        pass


VerbsEnum = graphene.Enum.from_enum(Message.Verbs)
MessageTypeEnum = graphene.Enum.from_enum(Message.MessageType)


class BaseMessageObjectType:
    action_object = graphene.Field(relay.Node)
    verb = graphene.Field(VerbsEnum)
    message_type = graphene.Field(MessageTypeEnum)
    content = graphene.String(required=False, profile_id=graphene.ID(required=False))
    is_read = graphene.Boolean(profile_id=graphene.ID(required=False))

    class Meta:
        interfaces = (relay.Node,)
        model = Message
        fields = (
            "id",
            "verb",
            "content",
            "message_type",
            "user",
            "profile",
            "created",
            "room",
            "action_object",
            "extra_data",
            "in_reply_to",
            "is_read",
            "deleted",
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

    @staticmethod
    def get_profile_pk(info, profile_id=None):
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            if not Profile.objects.get_if_member(pk=profile_pk, user=info.context.user):
                return None
            else:
                return profile_pk
        elif hasattr(info.context.user, "current_profile") and hasattr(
            info.context.user.current_profile, "pk"
        ):
            return info.context.user.current_profile.pk
        elif hasattr(info.context.user, "profile") and hasattr(info.context.user.profile, "pk"):
            return info.context.user.profile.pk
        else:
            return None

    @staticmethod
    def get_replaced_profile_name(profile, profile_pk, replacement_text):
        if not profile:
            return None
        elif profile.id == profile_pk:
            return replacement_text
        else:
            return profile.name

    @staticmethod
    def resolve_content(root, info, profile_id=None, **kwargs):
        profile_pk = BaseMessageObjectType.get_profile_pk(info, profile_id)
        if not profile_pk:
            return None
        if root.deleted:
            if profile_pk == root.profile.pk:
                return "You deleted this message"
            return "This message was deleted"
        if root.message_type == Message.MessageType.USER_MESSAGE:
            return root.content

        linked_capital_name = BaseMessageObjectType.get_replaced_profile_name(
            root.content_linked_profile_actor, profile_pk, "You"
        )
        linked_small_name = BaseMessageObjectType.get_replaced_profile_name(
            root.content_linked_profile_target, profile_pk, "you"
        )
        return root.content.format(
            content_linked_profile_actor=linked_capital_name,
            content_linked_profile_target=linked_small_name,
        )

    @staticmethod
    def resolve_is_read(root, info, profile_id=None, **kwargs):
        profile_pk = BaseMessageObjectType.get_profile_pk(info, profile_id)
        if not profile_pk:
            return None

        message_status = root.statuses.filter(profile_id=profile_pk).first()
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
        if self.is_group:
            profile = (
                info.context.user.current_profile
                if hasattr(info.context.user, "current_profile")
                else (
                    info.context.user.profile.pk if hasattr(info.context.user, "profile") else None
                )
            )
            participant = self.participants.filter(profile=profile).first()
            if participant:
                return self.messages.filter(created__gte=participant.accepted_at).order_by(
                    "-created"
                )
        return self.messages.all().order_by("-created")

    def resolve_participants(self, info, **kwargs):
        if self.is_group:
            profile = (
                info.context.user.current_profile
                if hasattr(info.context.user, "current_profile")
                else (info.context.user.profile if hasattr(info.context.user, "profile") else None)
            )
            participant = self.participants.filter(profile=profile).first()
            if participant:
                return self.participants.all().order_by(
                    Case(When(id=participant.id, then=0), default=1),
                    "-role",
                    "profile__name",
                )
        return self.participants.all()

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
            "participants_count",
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
