import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import swapper
from django.core.mail import send_mail
from django.db.models import Q
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from .groups import (
    ALL_VERBS_SETTING,
    NotificationGroup,
    get_notification_group_for_verb,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def render_verb_template_or_default(verb, context, template_type, extension) -> str:
    try:
        return render_to_string(
            f"emails/notifications/{verb}-{template_type}.{extension}.j2",
            context=context,
        )
    except TemplateDoesNotExist:
        logging.warning(
            f"Template emails/notifications/{verb}-{template_type}.{extension}.j2 does not exist, falling back to default template"
        )
        return render_to_string(
            f"emails/notification-{template_type}.{extension}.j2",
            context=context,
        )


def send_email_notification(to, context) -> None:
    verb = slugify(context["verb"])

    subject = render_verb_template_or_default(verb, context, "subject", "txt")
    subject = " ".join(subject.strip().split())

    text_message = render_verb_template_or_default(verb, context, "body", "txt")
    html_message = render_verb_template_or_default(verb, context, "body", "html")

    send_mail(
        subject, text_message, html_message=html_message, from_email=None, recipient_list=[to]
    )


def get_setting_verbs(verb: str) -> set[str]:
    """``NotificationSetting.verb`` values whose rows govern ``verb``.

    Always the verb's first segment (``chats.new`` -> ``chats``) and the global ``_ALL_``; plus the
    key of the registered notification group owning the verb, when there is one.
    """
    setting_verbs = {get_setting_from_verb(verb), ALL_VERBS_SETTING}
    group = get_notification_group_for_verb(verb)
    if group is not None:
        setting_verbs.add(group.key)
    return setting_verbs


def can_user_receive_notification(user_id, verb, channel) -> bool:
    """Whether ``user_id`` receives ``verb`` on ``channel``.

    A missing setting means allowed. Any inactive row for the channel or for ``ALL`` (on the
    verb's setting key or on ``_ALL_``) mutes it. Verbs of a locked group are always delivered.
    """
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    group = get_notification_group_for_verb(verb)
    if group is not None and group.is_locked:
        return True

    user_setting = (
        NotificationSetting.objects.filter(
            Q(channel=channel) | Q(channel=NotificationSetting.NotificationChannelTypes.ALL),
            verb__in=get_setting_verbs(verb),
            user_id=user_id,
        )
        .order_by("is_active")
        .first()
    )

    if user_setting:
        return user_setting.is_active
    return True


def get_setting_from_verb(verb) -> str:
    """ "
    Returns the setting group from the verb if available, otherwise returns the verb itself
        'CHATS.SEND_MESSAGE' -> 'CHATS'
        'SEND_MESSAGE' -> 'SEND_MESSAGE'
    """
    return verb.split(".")[0] if "." in verb else verb


@dataclass(frozen=True)
class NotificationGroupChannelState:
    channel: int
    is_active: bool


@dataclass(frozen=True)
class NotificationGroupState:
    """A notification group as seen by one user: its metadata plus per-channel state."""

    group: NotificationGroup
    channels: list[NotificationGroupChannelState]

    @property
    def key(self) -> str:
        return self.group.key

    @property
    def label(self) -> str:
        return str(self.group.label)

    @property
    def description(self) -> str | None:
        return str(self.group.description) if self.group.description else None

    @property
    def is_locked(self) -> bool:
        return self.group.is_locked


def get_notification_group_states(
    user: "AbstractBaseUser", groups: Iterable[NotificationGroup]
) -> list[NotificationGroupState]:
    """Per-channel ``is_active`` of ``groups`` for ``user``, with a single query.

    Matches ``can_user_receive_notification(user.pk, group.key, channel)`` for every channel.
    """
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    channel_all = int(NotificationSetting.NotificationChannelTypes.ALL)
    groups = list(groups)
    # The rows can_user_receive_notification checks for the group key itself.
    setting_verbs = {
        group.key: {get_setting_from_verb(group.key), group.key, ALL_VERBS_SETTING}
        for group in groups
    }

    inactive: set[tuple[str, int]] = set()
    if groups:
        inactive = set(
            NotificationSetting.objects.filter(
                user=user,
                is_active=False,
                verb__in=set().union(*setting_verbs.values()),
            ).values_list("verb", "channel")
        )

    def is_active(group: NotificationGroup, channel: int) -> bool:
        if group.is_locked:
            return True
        return not any(
            (verb, row_channel) in inactive
            for verb in setting_verbs[group.key]
            for row_channel in (channel, channel_all)
        )

    return [
        NotificationGroupState(
            group=group,
            channels=[
                NotificationGroupChannelState(channel=channel, is_active=is_active(group, channel))
                for channel in group.channels
            ],
        )
        for group in groups
    ]


def _set_setting(user: "AbstractBaseUser", verb: str, channel: int, is_active: bool) -> None:
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    updated = NotificationSetting.objects.filter(user=user, verb=verb, channel=channel).update(
        is_active=is_active, modified=timezone.now()
    )
    if not updated:
        NotificationSetting.objects.create(
            user=user, verb=verb, channel=channel, is_active=is_active
        )


def set_notification_group_setting(
    user: "AbstractBaseUser", group: NotificationGroup, channel: int, is_active: bool
) -> None:
    """Set (never toggle) ``user``'s preference for ``group`` on ``channel``.

    ``ALL`` sets the master row and every channel of the group to ``is_active``. Turning one
    channel on lifts an inactive ``ALL`` row, keeping the group's other channels off so only the
    requested channel changes.
    """
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    channel_all = int(NotificationSetting.NotificationChannelTypes.ALL)
    channel = int(channel)

    if channel == channel_all:
        _set_setting(user, group.key, channel_all, is_active)
        for group_channel in group.channels:
            _set_setting(user, group.key, group_channel, is_active)
        return

    if is_active:
        muted_by_all = NotificationSetting.objects.filter(
            user=user, verb=group.key, channel=channel_all, is_active=False
        )
        if muted_by_all.exists():
            for group_channel in group.channels:
                if group_channel != channel:
                    _set_setting(user, group.key, group_channel, False)
            muted_by_all.update(is_active=True, modified=timezone.now())

    _set_setting(user, group.key, channel, is_active)
