from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import BlocksInterface


def get_blocks_interface() -> type["BlocksInterface"]:
    from .object_types import BlocksInterface

    return BlocksInterface
