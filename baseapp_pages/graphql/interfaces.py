from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import PageInterface


def get_page_interface() -> type["PageInterface"]:
    from .object_types import PageInterface

    return PageInterface
