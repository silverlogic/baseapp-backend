import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.timesince import timesince as djtimesince
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import random_name_in


class AbstractBaseChatRoom(TimeStampedModel, RelayModel):
    title = models.CharField(max_length=255, blank=True, null=True)
    image = models.ImageField(
        _("image"), upload_to=random_name_in("chat_room_images"), blank=True, null=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="created_rooms", on_delete=models.CASCADE
    )
    last_message = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "Message"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    last_message_time = models.DateTimeField(null=True, blank=True, default=timezone.now)
    participants_count = models.IntegerField(default=0)
    messages_count = models.IntegerField(default=0)
    is_group = models.BooleanField(default=False)

    class Meta:
        abstract = True
        ordering = ["-last_message_time", "-created"]

    def __str__(self):
        return str(self.pk)

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ChatRoomObjectType

        return ChatRoomObjectType


class AbstractBaseMessage(TimeStampedModel, RelayModel):
    class Verbs(models.IntegerChoices):
        SENT_MESSAGE = 100, _("sent a message")

    class MessageType(models.IntegerChoices):
        USER_MESSAGE = 1, _("User message")
        SYSTEM_GENERATED = 2, _("System message")

    @property
    def description(self):
        return self.label

    content = models.TextField(null=True, blank=True)
    content_linked_profile_actor = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="linked_as_content_actor_set",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    content_linked_profile_target = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        related_name="linked_as_content_target_set",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    message_type = models.IntegerField(
        choices=MessageType.choices, default=MessageType.USER_MESSAGE
    )
    verb = models.IntegerField(choices=Verbs.choices, default=Verbs.SENT_MESSAGE, db_index=True)

    room = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "ChatRoom"),
        blank=True,
        null=True,
        related_name="messages",
        on_delete=models.CASCADE,
        db_index=True,
    )

    in_reply_to = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "Message"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )

    action_object_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        related_name="action_object",
        on_delete=models.CASCADE,
        db_index=True,
    )
    action_object_object_id = models.IntegerField(blank=True, null=True, db_index=True)
    action_object = GenericForeignKey("action_object_content_type", "action_object_object_id")
    deleted = models.BooleanField(default=False)

    extra_data = models.JSONField(blank=True, null=True)

    class Meta:
        abstract = True
        ordering = ["-created"]

    def __str__(self):
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

    def timesince(self, now=None):
        """
        Shortcut for the ``django.utils.timesince.timesince`` function of the
        current timestamp.
        """
        return (
            djtimesince(self.created, now).encode("utf8").replace(b"\xc2\xa0", b" ").decode("utf8")
        )

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import MessageObjectType

        return MessageObjectType

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)

        if created:
            from baseapp_chats.graphql.subscriptions import (
                ChatRoomOnMessagesCountUpdate,
            )

            for participant in self.room.participants.all():
                if participant.profile_id != self.profile_id:
                    ChatRoomOnMessagesCountUpdate.send_updated_chat_count(
                        profile=participant.profile, profile_id=participant.profile.relay_id
                    )


class AbstractChatRoomParticipant(TimeStampedModel, RelayModel):
    class ChatRoomParticipantRoles(models.IntegerChoices):
        MEMBER = 1, _("member")
        ADMIN = 2, _("admin")

        @property
        def description(self):
            return self.label

    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    room = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "ChatRoom"),
        related_name="participants",
        on_delete=models.CASCADE,
    )
    role = models.IntegerField(
        choices=ChatRoomParticipantRoles.choices, default=ChatRoomParticipantRoles.MEMBER
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    has_archived_room = models.BooleanField(default=False)

    class Meta:
        abstract = True
        ordering = ["-role", "profile__name"]

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ChatRoomParticipantObjectType

        return ChatRoomParticipantObjectType


class AbstractUnreadMessageCount(RelayModel):
    room = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "ChatRoom"),
        related_name="unread_messages",
        on_delete=models.CASCADE,
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"), on_delete=models.CASCADE
    )
    marked_unread = models.BooleanField(default=False)
    count = models.IntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["id"]
        unique_together = ["room_id", "profile_id"]


class AbstractMessageStatus(RelayModel):
    message = models.ForeignKey(
        swapper.get_model_name("baseapp_chats", "Message"),
        on_delete=models.CASCADE,
        related_name="statuses",
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"), on_delete=models.CASCADE
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        unique_together = ["message_id", "profile_id"]
