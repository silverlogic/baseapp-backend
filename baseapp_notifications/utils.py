import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import swapper
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
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


def send_notification_email(recipient: Any, notification: Any, **context: Any) -> None:
    """Default ``BASEAPP_NOTIFICATIONS_EMAIL_SENDER``: render the ``.j2`` templates and send_mail."""
    send_email_notification(
        to=recipient.email,
        context=dict(notification=notification, recipient=recipient, **context),
    )


def get_setting_verbs(verb: str, channel: int | None = None) -> set[str]:
    """``NotificationSetting.verb`` values whose rows govern ``verb`` on ``channel``.

    A verb outside every group: its first segment (``chats.new`` -> ``chats``) and the global
    ``_ALL_``, as before groups existed. A verb owned by a group: the group key and ``_ALL_`` only,
    so another group's row (a parent ``chats`` over ``chats.mentions``, or the first segment of a
    verb listed in ``verbs``) never overrides the group's own preference. On a concrete channel
    the group does not offer, only ``_ALL_`` applies.
    """
    group = get_notification_group_for_verb(verb)
    if group is None:
        return {get_setting_from_verb(verb), ALL_VERBS_SETTING}

    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    if (
        channel is not None
        and int(channel) != NotificationSetting.NotificationChannelTypes.ALL
        and int(channel) not in group.channels
    ):
        return {ALL_VERBS_SETTING}
    return {group.key, ALL_VERBS_SETTING}


def can_user_receive_notification(user_id, verb, channel) -> bool:
    """Whether ``user_id`` receives ``verb`` on ``channel``.

    A missing setting means allowed. Any inactive row for the channel or for ``ALL`` (on one of
    :func:`get_setting_verbs`) mutes it. Verbs of a locked group are always delivered.
    """
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    group = get_notification_group_for_verb(verb)
    if group is not None and group.is_locked:
        return True

    user_setting = (
        NotificationSetting.objects.filter(
            Q(channel=channel) | Q(channel=NotificationSetting.NotificationChannelTypes.ALL),
            verb__in=get_setting_verbs(verb, channel),
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

    Matches ``can_user_receive_notification(user.pk, verb, channel)`` for every verb of each
    group and every channel the group offers.
    """
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    channel_all = int(NotificationSetting.NotificationChannelTypes.ALL)
    groups = list(groups)
    # The rows get_setting_verbs returns for any verb of the group on one of its channels.
    setting_verbs = {group.key: {group.key, ALL_VERBS_SETTING} for group in groups}

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

    ``ALL`` sets every channel of the group to ``is_active``; it writes no ``ALL`` row, and only
    updates one left behind by ``notificationSettingToggle``. Turning one channel on lifts such an
    inactive ``ALL`` row, keeping the group's other channels off so only the requested channel
    changes.
    """
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    channel_all = int(NotificationSetting.NotificationChannelTypes.ALL)
    channel = int(channel)
    all_rows = NotificationSetting.objects.filter(user=user, verb=group.key, channel=channel_all)

    with transaction.atomic():
        # Rows have no unique constraint: lock the user so concurrent update-or-create calls for
        # the same user cannot both create a row.
        list(
            get_user_model()
            .objects.select_for_update()
            .filter(pk=user.pk)
            .values_list("pk", flat=True)
        )

        if channel == channel_all:
            for group_channel in group.channels:
                _set_setting(user, group.key, group_channel, is_active)
            all_rows.update(is_active=is_active, modified=timezone.now())
            return

        if is_active and all_rows.filter(is_active=False).exists():
            for group_channel in group.channels:
                if group_channel != channel:
                    _set_setting(user, group.key, group_channel, False)
            all_rows.update(is_active=True, modified=timezone.now())

        _set_setting(user, group.key, channel, is_active)
