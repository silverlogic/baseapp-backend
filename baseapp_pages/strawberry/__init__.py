from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import PageInterface


def get_page_interface() -> type["PageInterface"]:
    from .interfaces import PageInterface

    return PageInterface
