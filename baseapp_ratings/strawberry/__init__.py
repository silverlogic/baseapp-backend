from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import RatingsInterface


def get_ratings_interface() -> type["RatingsInterface"]:
    from .interfaces import RatingsInterface

    return RatingsInterface
