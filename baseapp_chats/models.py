import logging
from typing import TYPE_CHECKING

import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone
from django.utils.timesince import timesince as djtimesince
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin, random_name_in
from baseapp_core.pghelpers import pgtrigger_register_default_track
from baseapp_core.swapper import init_swapped_models

from .triggers import (
    create_message_status_trigger,
    decrement_unread_count_trigger,
    increment_unread_count_trigger,
    set_last_message_on_insert_trigger,
    update_last_message_on_delete_trigger,
)

if TYPE_CHECKING:
    from baseapp_core.graphql import DjangoObjectType

logger = logging.getLogger(__name__)


class AbstractBaseChatRoom(TimeStampedModel, DocumentIdMixin, RelayModel):
    title = models.CharField(_("title"), max_length=255, blank=True, null=True)
    image = models.ImageField(
        _("image"), upload_to=random_name_in("chat_room_images"), blank=True, null=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_rooms",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("created by"),
    )
    created_by_profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="profile_created_rooms",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("created by profile"),
    )
    last_message = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "Message"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("last message"),
    )
    last_message_time = models.DateTimeField(
        _("last message time"), null=True, blank=True, default=timezone.now
    )
    participants_count = models.IntegerField(_("participants count"), default=0)
    messages_count = models.IntegerField(_("messages count"), default=0)
    is_group = models.BooleanField(_("group"), default=False)

    class Meta:
        abstract = True
        ordering = ["-last_message_time", "-created"]
        swappable = swapper.swappable_setting("baseapp_chats", "ChatRoom")
        verbose_name = _("chat room")
        verbose_name_plural = _("chat rooms")

    def __str__(self) -> str:
        return str(self.pk)

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import ChatRoomObjectType

        return ChatRoomObjectType


class AbstractBaseMessage(TimeStampedModel, DocumentIdMixin, RelayModel):
    class Verbs(models.IntegerChoices):
        SENT_MESSAGE = 100, _("sent a message")

    class MessageType(models.IntegerChoices):
        USER_MESSAGE = 1, _("User message")
        SYSTEM_GENERATED = 2, _("System message")

    @property
    def description(self) -> str:
        return self.label

    content = models.TextField(_("content"), null=True, blank=True)
    content_linked_profile_actor = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="linked_as_content_actor_set",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("content linked profile actor"),
    )
    content_linked_profile_target = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="linked_as_content_target_set",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("content linked profile target"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("user"),
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("profile"),
    )

    message_type = models.IntegerField(
        _("message type"), choices=MessageType.choices, default=MessageType.USER_MESSAGE
    )
    verb = models.IntegerField(
        _("verb"), choices=Verbs.choices, default=Verbs.SENT_MESSAGE, db_index=True
    )

    room = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "ChatRoom"),
        blank=True,
        null=True,
        related_name="messages",
        on_delete=models.CASCADE,
        db_index=True,
        verbose_name=_("room"),
    )

    in_reply_to = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "Message"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name=_("in reply to"),
    )

    action_object_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        related_name="+",
        on_delete=models.CASCADE,
        db_index=True,
        verbose_name=_("action object content type"),
    )
    action_object_object_id = models.IntegerField(
        _("action object id"), blank=True, null=True, db_index=True
    )
    action_object = GenericForeignKey("action_object_content_type", "action_object_object_id")
    deleted = models.BooleanField(_("deleted"), default=False)

    extra_data = models.JSONField(_("extra data"), blank=True, null=True)

    class Meta:
        abstract = True
        ordering = ["-created"]
        swappable = swapper.swappable_setting("baseapp_chats", "Message")
        verbose_name = _("message")
        verbose_name_plural = _("messages")

    def __str__(self) -> str:
        ctx = {
            "actor": (
                self.profile if self.message_type == self.MessageType.USER_MESSAGE else "The system"
            ),
            "verb": self.__class__.Verbs(self.verb).label,
            "action_object": self.action_object,
            "target": self.room,
            "timesince": self.timesince(),
        }
        if self.room:
            if self.action_object:
                return (
                    _("%(actor)s %(verb)s %(action_object)s on %(target)s %(timesince)s ago") % ctx
                )
            return _("%(actor)s %(verb)s on %(target)s %(timesince)s ago") % ctx
        if self.action_object:
            return _("%(actor)s %(verb)s %(action_object)s %(timesince)s ago") % ctx
        return _("%(actor)s %(verb)s %(timesince)s ago") % ctx

    def timesince(self, now=None) -> str:
        """
        Shortcut for the ``django.utils.timesince.timesince`` function of the
        current timestamp.
        """
        return (
            djtimesince(self.created, now).encode("utf8").replace(b"\xc2\xa0", b" ").decode("utf8")
        )

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import MessageObjectType

        return MessageObjectType

    def save(self, *args, **kwargs) -> None:
        created = self._state.adding
        super().save(*args, **kwargs)

        if not created or self.room is None:
            return

        # Materialise inside the current transaction with the Profile
        # FK pulled in one query so the on_commit callback doesn't
        # re-hit the DB and doesn't fan out as N+1.
        participants = list(
            self.room.participants.select_related("profile").exclude(profile_id=self.profile_id)
        )
        if not participants:
            return

        def _broadcast_unread_counts() -> None:
            from baseapp_chats.graphql.subscriptions import (
                ChatRoomOnMessagesCountUpdate,
            )

            for participant in participants:
                try:
                    ChatRoomOnMessagesCountUpdate.send_updated_chat_count(
                        profile=participant.profile,
                        profile_id=participant.profile.relay_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to broadcast unread-count update to profile_id=%s",
                        participant.profile_id,
                    )

        transaction.on_commit(_broadcast_unread_counts)


class AbstractChatRoomParticipant(TimeStampedModel, DocumentIdMixin, RelayModel):
    class ChatRoomParticipantRoles(models.IntegerChoices):
        MEMBER = 1, _("member")
        ADMIN = 2, _("admin")

        @property
        def description(self) -> str:
            return self.label

    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("profile"),
    )
    room = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "ChatRoom"),
        related_name="participants",
        on_delete=models.CASCADE,
        verbose_name=_("room"),
    )
    role = models.IntegerField(
        _("role"),
        choices=ChatRoomParticipantRoles.choices,
        default=ChatRoomParticipantRoles.MEMBER,
    )
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)
    has_archived_room = models.BooleanField(_("has archived room"), default=False)

    class Meta:
        abstract = True
        ordering = ["-role", "profile__name"]
        swappable = swapper.swappable_setting("baseapp_chats", "ChatRoomParticipant")
        verbose_name = _("chat room participant")
        verbose_name_plural = _("chat room participants")

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import ChatRoomParticipantObjectType

        return ChatRoomParticipantObjectType


class AbstractUnreadMessageCount(DocumentIdMixin, RelayModel):
    room = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "ChatRoom"),
        related_name="unread_messages",
        on_delete=models.CASCADE,
        verbose_name=_("room"),
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        on_delete=models.CASCADE,
        verbose_name=_("profile"),
    )
    marked_unread = models.BooleanField(_("marked unread"), default=False)
    count = models.IntegerField(_("count"), default=0)

    class Meta:
        abstract = True
        ordering = ["id"]
        unique_together = ["room_id", "profile_id"]
        swappable = swapper.swappable_setting("baseapp_chats", "UnreadMessageCount")
        verbose_name = _("unread message count")
        verbose_name_plural = _("unread message counts")


class AbstractMessageStatus(DocumentIdMixin, RelayModel):
    message = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "Message"),
        on_delete=models.CASCADE,
        related_name="statuses",
        verbose_name=_("message"),
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        on_delete=models.CASCADE,
        verbose_name=_("profile"),
    )
    is_read = models.BooleanField(_("read"), default=False)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    class Meta:
        abstract = True
        unique_together = ["message_id", "profile_id"]
        swappable = swapper.swappable_setting("baseapp_chats", "MessageStatus")
        verbose_name = _("message status")
        verbose_name_plural = _("message statuses")


# Resolve the concrete swap targets (e.g. social_chats.ChatRoom) so the
# triggers below can be wired with real db_table names. Order matters:
# Message references ChatRoom + ChatRoomParticipant, MessageStatus
# references Message + UnreadMessageCount.
ChatRoom, ChatRoomParticipant, Message, UnreadMessageCount, MessageStatus = init_swapped_models(
    [
        ("baseapp_chats", "ChatRoom"),
        ("baseapp_chats", "ChatRoomParticipant"),
        ("baseapp_chats", "Message"),
        ("baseapp_chats", "UnreadMessageCount"),
        ("baseapp_chats", "MessageStatus"),
    ]
)


# Default domain triggers. Mirrors the pghistory_register_default_track
# contract: consumers can swap a chats model and override these via
# `@pgtrigger_register_track(...)` on the concrete model.
pgtrigger_register_default_track(
    Message,
    [
        set_last_message_on_insert_trigger(ChatRoom),
        create_message_status_trigger(ChatRoomParticipant, AbstractBaseMessage.MessageType),
        update_last_message_on_delete_trigger(ChatRoom),
    ],
)

pgtrigger_register_default_track(
    MessageStatus,
    [
        increment_unread_count_trigger(UnreadMessageCount, Message),
        decrement_unread_count_trigger(UnreadMessageCount, Message),
    ],
)
