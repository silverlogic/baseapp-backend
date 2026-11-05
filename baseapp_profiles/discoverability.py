from typing import TYPE_CHECKING, Callable, Optional

from django.conf import settings
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.db.models import QuerySet


def get_discoverable_profiles_filter() -> Optional[Callable]:
    """
    The project's `BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER`: a dotted path to (or a)
    `callable(queryset, user) -> queryset`, or None when the project sets none.
    """
    hook = getattr(settings, "BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER", None)
    if isinstance(hook, str):
        return import_string(hook)
    return hook


def filter_discoverable_profiles(
    queryset: "QuerySet", user: "AbstractBaseUser | AnonymousUser"
) -> "QuerySet":
    """
    Narrow `queryset` to the profiles `user` may find in lists and searches.

    Returns `queryset` unchanged when no filter is configured. This only decides what a
    user can discover; it is not a permission check, so `view_profile` still governs
    fetching a profile directly.
    """
    hook = get_discoverable_profiles_filter()
    if hook is None:
        return queryset
    return hook(queryset, user)
