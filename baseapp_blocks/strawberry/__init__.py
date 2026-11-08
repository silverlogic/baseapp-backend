from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import BlocksInterface


def get_blocks_interface() -> type["BlocksInterface"]:
    from .types import BlocksInterface

    return BlocksInterface
