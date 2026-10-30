import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import swapper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import get_template, render_to_string
from django.utils import timezone
from django.utils.text import slugify

from baseapp_core.i18n import user_language

from .groups import (
    ALL_VERBS_SETTING,
    NotificationGroup,
    get_notification_group_for_verb,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


NOTIFICATION_EMAIL_TEMPLATE_DIR = "emails/notifications"
DEFAULT_NOTIFICATION_EMAIL_TEMPLATE = "emails/notification"
NOTIFICATION_EMAIL_TEMPLATE_PARTS = (("subject", "txt"), ("body", "txt"), ("body", "html"))
EMAIL_OPTION_KEYS = ("from_email", "reply_to", "cc", "bcc", "attachments")
EMAIL_ADDRESS_LIST_OPTION_KEYS = ("reply_to", "cc", "bcc")
# Render-context keys the default sender always sets itself; ``email_context`` cannot replace them.
RESERVED_EMAIL_CONTEXT_KEYS = ("notification", "recipient", "verb")


def validate_email_context(email_context: Mapping | None) -> None:
    """Raise when ``email_context`` is not a mapping or sets a reserved render key."""
    if email_context is None:
        return
    if not isinstance(email_context, Mapping):
        raise TypeError("email_context must be a dict.")
    if reserved := sorted(set(email_context) & set(RESERVED_EMAIL_CONTEXT_KEYS)):
        raise ValueError(f"email_context cannot set the reserved keys {', '.join(reserved)}.")


def validate_email_options(email_options: Mapping | None) -> None:
    """Raise when ``email_options`` is not a mapping or ``reply_to``, ``cc`` or ``bcc`` is not a
    string, list or tuple. Other keys are left to the sender."""
    if email_options is None:
        return
    if not isinstance(email_options, Mapping):
        raise TypeError("email_options must be a dict.")
    for key in EMAIL_ADDRESS_LIST_OPTION_KEYS:
        value = email_options.get(key)
        if value is not None and not isinstance(value, (str, list, tuple)):
            raise TypeError(f"email_options[{key!r}] must be a string or a list/tuple of strings.")


def get_email_message_options(options: Mapping | None) -> dict:
    """The ``EmailMultiAlternatives`` keyword arguments in ``options``; a single address is listed."""
    validate_email_options(options)
    options = {key: value for key, value in (options or {}).items() if key in EMAIL_OPTION_KEYS}
    for key in EMAIL_ADDRESS_LIST_OPTION_KEYS:
        if isinstance(options.get(key), str):
            options[key] = [options[key]]
    return options


def _template_exists(name: str) -> bool:
    try:
        get_template(name)
    except TemplateDoesNotExist:
        return False
    return True


def _has_notification_email_template(base: str) -> bool:
    return any(
        _template_exists(f"{base}-{part}.{extension}.j2")
        for part, extension in NOTIFICATION_EMAIL_TEMPLATE_PARTS
    )


def get_notification_email_template_bases(
    verb: str, template: str | None = None
) -> list[str] | None:
    """Template bases to render the email of ``verb`` from, each part from the first that has it.

    An explicit ``template`` is followed by ``emails/notification``. Otherwise the bases are
    ``emails/notifications/{verb}`` (the raw verb, dots kept) and the legacy
    ``emails/notifications/{slugify(verb)}`` that have at least one part, then
    ``emails/notification``. With ``BASEAPP_NOTIFICATIONS_EMAIL_REQUIRE_VERB_TEMPLATE = True`` a
    verb with neither returns ``None``: it must not be emailed.
    """
    if template:
        bases = [template]
    else:
        bases = [
            f"{NOTIFICATION_EMAIL_TEMPLATE_DIR}/{name}"
            for name in dict.fromkeys((verb, slugify(verb)))
            if name
            and _has_notification_email_template(f"{NOTIFICATION_EMAIL_TEMPLATE_DIR}/{name}")
        ]
        if not bases and getattr(
            settings, "BASEAPP_NOTIFICATIONS_EMAIL_REQUIRE_VERB_TEMPLATE", False
        ):
            return None
    return list(dict.fromkeys((*bases, DEFAULT_NOTIFICATION_EMAIL_TEMPLATE)))


def resolve_notification_email_template(verb: str, template: str | None = None) -> str | None:
    """Base name of the email templates for ``verb``, or ``None`` when it must not be emailed.

    The parts are ``{base}-subject.txt.j2``, ``{base}-body.txt.j2`` and ``{base}-body.html.j2``.
    This is the first of :func:`get_notification_email_template_bases`: ``template`` when given,
    else ``emails/notifications/{verb}``, ``emails/notifications/{slugify(verb)}`` or
    ``emails/notification``, whichever first has a part.
    """
    bases = get_notification_email_template_bases(verb, template)
    return bases[0] if bases else None


def render_verb_template_or_default(verb, context, template_type, extension) -> str:
    """Render ``template_type`` of the templates of ``verb`` (used as given), or the default."""
    name = f"{NOTIFICATION_EMAIL_TEMPLATE_DIR}/{verb}-{template_type}.{extension}.j2"
    try:
        return render_to_string(name, context=context)
    except TemplateDoesNotExist:
        logger.warning("Template %s does not exist, falling back to default template", name)
        return render_to_string(
            f"{DEFAULT_NOTIFICATION_EMAIL_TEMPLATE}-{template_type}.{extension}.j2",
            context=context,
        )


def send_email_notification(
    to, context, template: str | None = None, options: dict | None = None
) -> bool:
    """Render the notification email for ``context["verb"]`` and send it to ``to``.

    ``template`` is an explicit template base (see :func:`resolve_notification_email_template`).
    Each part comes from the first of :func:`get_notification_email_template_bases` that has it.
    ``options`` may hold ``from_email``, ``reply_to``, ``cc``, ``bcc`` (a string or a list) and
    ``attachments`` (``(filename, content, mimetype)`` tuples or MIME objects); other keys are
    ignored. Returns ``False`` when no template applies and nothing was sent.
    """
    bases = get_notification_email_template_bases(context["verb"], template)
    if bases is None:
        return False

    def render(part: str, extension: str) -> str:
        return render_to_string([f"{base}-{part}.{extension}.j2" for base in bases], context)

    with user_language(context.get("recipient")):
        subject = " ".join(render("subject", "txt").strip().split())
        text_message = render("body", "txt")
        html_message = render("body", "html")

    message = EmailMultiAlternatives(
        subject, text_message, to=[to], **get_email_message_options(options)
    )
    message.attach_alternative(html_message, "text/html")
    message.send()
    return True


def send_notification_email(
    recipient: Any,
    notification: Any,
    *,
    email_template: str | None = None,
    email_context: dict | None = None,
    email_options: dict | None = None,
    **context: Any,
) -> bool:
    """Default ``BASEAPP_NOTIFICATIONS_EMAIL_SENDER``: render the ``.j2`` templates and send.

    ``email_template`` replaces the verb's templates, ``email_context`` is added to the render
    context (overriding any key but ``notification``, ``recipient`` and ``verb``) and
    ``email_options`` is passed on as ``options`` to :func:`send_email_notification`.
    """
    validate_email_context(email_context)
    return send_email_notification(
        to=recipient.email,
        context={
            **context,
            **(email_context or {}),
            "notification": notification,
            "recipient": recipient,
        },
        template=email_template,
        options=email_options,
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
