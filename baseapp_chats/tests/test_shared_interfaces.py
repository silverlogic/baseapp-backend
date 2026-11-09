"""Tests for the `ChatRoomsInterface` shared-interface registration.

The interface is registered by name (`"ChatRoomsInterface"`) in
`apps.py.register_strawberry_shared_interfaces`. Consumers like
`baseapp_profiles` opt in via
`strawberry_shared_interfaces.get("ChatRoomsInterface")` — no
direct import. These tests pin that contract.
"""

from baseapp_chats.strawberry import get_chat_rooms_interface
from baseapp_chats.strawberry.interfaces import ChatRoomsInterface
from baseapp_core.plugins import strawberry_shared_interfaces


def test_chat_rooms_interface_is_registered_by_name() -> None:
    iface = strawberry_shared_interfaces.get_interface("ChatRoomsInterface")
    assert iface is ChatRoomsInterface


def test_get_chat_rooms_interface_returns_interface_class() -> None:
    """The registry value is a lazy callable — invoking it returns the
    Interface class. Test the callable directly so a future move to
    eager registration doesn't silently change the return shape."""
    assert get_chat_rooms_interface() is ChatRoomsInterface


def test_profile_type_picks_up_chat_rooms_interface() -> None:
    """`baseapp_profiles.strawberry.types.ProfileType` composes its
    interfaces via `strawberry_shared_interfaces.get(...,
    "ChatRoomsInterface")`. The interface must appear in the consumer's
    bases — catches a regression where the by-name lookup is dropped from
    the consumer or the registry name diverges."""
    from baseapp_profiles.strawberry.types import ProfileType

    assert issubclass(ProfileType, ChatRoomsInterface)
