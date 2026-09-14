from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import RatingsInterface


def get_ratings_interface() -> type["RatingsInterface"]:
    from .object_types import RatingsInterface

    return RatingsInterface
