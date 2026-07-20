from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import ReportsInterface


def get_reports_interface() -> type["ReportsInterface"]:
    from .object_types import ReportsInterface

    return ReportsInterface
