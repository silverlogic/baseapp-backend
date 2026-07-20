"""Tests for the `ChatRoomsInterface` shared-interface registration.

The interface is registered by name (`"ChatRoomsInterface"`) in
`apps.py.register_graphql_shared_interfaces`. Consumers like
`baseapp_profiles` opt in via
`graphql_shared_interfaces.get(RelayNode, "ChatRoomsInterface")` — no
direct import. These tests pin that contract.
"""

from baseapp_chats.graphql.interfaces import ChatRoomsInterface
from baseapp_chats.graphql.shared_interfaces import get_chat_rooms_interface
from baseapp_core.plugins import graphql_shared_interfaces


def test_chat_rooms_interface_is_registered_by_name() -> None:
    iface = graphql_shared_interfaces.get_interface("ChatRoomsInterface")
    assert iface is ChatRoomsInterface


def test_get_chat_rooms_interface_returns_interface_class() -> None:
    """The registry value is a lazy callable — invoking it returns the
    Interface class. Test the callable directly so a future move to
    eager registration doesn't silently change the return shape."""
    assert get_chat_rooms_interface() is ChatRoomsInterface


def test_profile_object_type_picks_up_chat_rooms_interface() -> None:
    """`baseapp_profiles.graphql.object_types.ProfileObjectType` composes
    its interfaces via `graphql_shared_interfaces.get(...,
    "ChatRoomsInterface")`. The interface must appear in the consumer's
    final interface tuple — catches a regression where the by-name
    lookup is dropped from the consumer or the registry name diverges."""
    from baseapp_profiles.graphql.object_types import ProfileObjectType

    assert ChatRoomsInterface in ProfileObjectType._meta.interfaces
