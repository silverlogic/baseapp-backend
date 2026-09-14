from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import ProfileInterface, ProfilesInterface


def get_profile_interface() -> type["ProfileInterface"]:
    from .object_types import ProfileInterface

    return ProfileInterface


def get_profiles_list_interface() -> type["ProfilesInterface"]:
    from .object_types import ProfilesInterface

    return ProfilesInterface
