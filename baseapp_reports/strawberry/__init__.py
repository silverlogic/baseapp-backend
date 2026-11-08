from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import ReportsInterface


def get_reports_interface() -> type["ReportsInterface"]:
    from .interfaces import ReportsInterface

    return ReportsInterface
