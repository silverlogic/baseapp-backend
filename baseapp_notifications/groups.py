"""Registry of notification groups.

A notification group bundles related verbs under one user-facing preference ("Comments",
"Security alerts", ...). Projects register their groups from ``AppConfig.ready()``::

    from baseapp_notifications.groups import register_notification_group

    register_notification_group(
        "comments",
        label=_("Comments"),
        description=_("Replies and mentions on your posts"),
    )

The user's choices are stored as ``NotificationSetting`` rows whose ``verb`` is the group key, so
they are honoured by ``can_user_receive_notification`` for every verb of the group. Verbs that do
not belong to any group keep working exactly as before.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import swapper
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

ALL_VERBS_SETTING = "_ALL_"


def _channel_types() -> Any:
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    return NotificationSetting.NotificationChannelTypes


def _default_channels() -> tuple[int, ...]:
    types = _channel_types()
    return (int(types.IN_APP), int(types.EMAIL), int(types.PUSH))


def _coerce_channel(channel: Any) -> int:
    """Accept a ``NotificationChannelTypes`` member, its integer value or its name."""
    types = _channel_types()
    if isinstance(channel, str):
        try:
            value = int(types[channel.upper()])
        except KeyError:
            raise ImproperlyConfigured(f"Unknown notification channel {channel!r}")
    else:
        value = int(channel)
        if value not in types.values:
            raise ImproperlyConfigured(f"Unknown notification channel {channel!r}")
    if value == int(types.ALL):
        raise ImproperlyConfigured(
            "List the concrete channels of a notification group; ALL is implied."
        )
    return value


@dataclass(frozen=True)
class NotificationGroup:
    """A registered notification group. Build it with :func:`register_notification_group`."""

    key: str
    label: Any
    description: Any = ""
    verbs: tuple[str, ...] | None = None
    audience: Callable[["AbstractBaseUser"], bool] | None = None
    is_locked: bool = False
    channels: tuple[int, ...] = field(default_factory=tuple)

    def matches_verb(self, verb: str) -> bool:
        """Whether ``verb`` belongs to this group.

        The group key itself always matches. A group registered without ``verbs`` owns every
        verb under its key (``key`` or ``key.*``); a group with ``verbs`` owns exactly those.
        """
        if verb == self.key:
            return True
        if self.verbs is None:
            return verb.startswith(f"{self.key}.")
        return verb in self.verbs

    def is_visible_to(self, user: "AbstractBaseUser") -> bool:
        """Whether ``user`` may see and change this group's preferences."""
        if self.audience is None:
            return True
        return bool(self.audience(user))


class NotificationGroupRegistry:
    """Ordered, in-memory registry of :class:`NotificationGroup` keyed by ``key``."""

    def __init__(self) -> None:
        self._groups: dict[str, NotificationGroup] = {}

    def register(self, group: NotificationGroup) -> NotificationGroup:
        """Add ``group``; registering the same key again replaces it in place."""
        self._groups[group.key] = group
        return group

    def unregister(self, key: str) -> None:
        self._groups.pop(key, None)

    def clear(self) -> None:
        self._groups.clear()

    def get(self, key: str) -> NotificationGroup | None:
        return self._groups.get(key)

    def list(self, user: "AbstractBaseUser | None" = None) -> list[NotificationGroup]:
        """All groups in registration order, limited to those ``user`` may see when given."""
        groups = list(self._groups.values())
        if user is None:
            return groups
        return [group for group in groups if group.is_visible_to(user)]

    def get_for_verb(self, verb: str) -> NotificationGroup | None:
        """The group owning ``verb``.

        An exact match (the group key, or a verb listed in ``verbs``) wins; otherwise the
        prefix-matched group with the longest key wins, so ``chats.mentions`` beats ``chats``.
        """
        best: NotificationGroup | None = None
        for group in self._groups.values():
            if not group.matches_verb(verb):
                continue
            if verb == group.key or (group.verbs is not None and verb in group.verbs):
                return group
            if best is None or len(group.key) > len(best.key):
                best = group
        return best

    def is_registered_verb(self, verb: str) -> bool:
        return self.get_for_verb(verb) is not None


notification_groups = NotificationGroupRegistry()


def register_notification_group(
    key: str,
    *,
    label: Any,
    description: Any = "",
    verbs: Iterable[str] | None = None,
    audience: Callable[["AbstractBaseUser"], bool] | None = None,
    is_locked: bool = False,
    channels: Iterable[Any] | None = None,
) -> NotificationGroup:
    """Register (or replace) a notification group.

    Args:
        key: Stable identifier; stored as ``NotificationSetting.verb`` for the group's preferences.
        label: User-facing name (a lazy translation is fine).
        description: Optional user-facing help text.
        verbs: Verbs owned by the group. ``None`` (default) owns ``key`` and every ``key.*`` verb.
        audience: ``callable(user) -> bool`` deciding who sees the group. ``None`` means everyone.
        is_locked: Locked groups are always delivered and cannot be changed by users.
        channels: Channels users can configure (``NotificationChannelTypes`` members, values or
            names). Defaults to in-app, email and push.
    """
    if not key or not isinstance(key, str):
        raise ImproperlyConfigured("A notification group needs a non-empty string key.")
    if key == ALL_VERBS_SETTING:
        raise ImproperlyConfigured(f"{ALL_VERBS_SETTING!r} is reserved for the global setting.")
    if audience is not None and not callable(audience):
        raise ImproperlyConfigured("A notification group's audience must be callable.")

    resolved_channels = (
        _default_channels()
        if channels is None
        else tuple(dict.fromkeys(_coerce_channel(channel) for channel in channels))
    )
    if not resolved_channels:
        raise ImproperlyConfigured(f"Notification group {key!r} needs at least one channel.")

    return notification_groups.register(
        NotificationGroup(
            key=key,
            label=label,
            description=description,
            verbs=None if verbs is None else tuple(verbs),
            audience=audience,
            is_locked=is_locked,
            channels=resolved_channels,
        )
    )


def get_notification_group(key: str) -> NotificationGroup | None:
    return notification_groups.get(key)


def list_notification_groups(user: "AbstractBaseUser | None" = None) -> list[NotificationGroup]:
    return notification_groups.list(user)


def get_notification_group_for_verb(verb: str) -> NotificationGroup | None:
    return notification_groups.get_for_verb(verb)


def is_registered_verb(verb: str) -> bool:
    return notification_groups.is_registered_verb(verb)
