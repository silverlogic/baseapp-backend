from typing import Any


def get_profile_interface() -> Any:
    from .interfaces import ProfileInterface

    return ProfileInterface


def get_profiles_interface() -> Any:
    from .interfaces import ProfilesInterface

    return ProfilesInterface
