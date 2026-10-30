from typing import Any

from django.core.checks import Error, register

from .discoverability import get_discoverable_profiles_filter


def discoverable_profiles_filter_errors() -> list[Error]:
    """
    A `BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER` that cannot be loaded would otherwise
    only surface as an error on every `allProfiles` request, so report it at startup.
    """
    try:
        hook = get_discoverable_profiles_filter()
    except ImportError as exc:
        return [
            Error(
                f"BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER cannot be imported: {exc}",
                hint="Point it at a callable(queryset, user) -> queryset, or remove it.",
                id="baseapp_profiles.E001",
            )
        ]
    if hook is not None and not callable(hook):
        return [
            Error(
                "BASEAPP_PROFILES_DISCOVERABLE_PROFILES_FILTER is not callable.",
                hint="Point it at a callable(queryset, user) -> queryset, or remove it.",
                id="baseapp_profiles.E002",
            )
        ]
    return []


@register()
def check_discoverable_profiles_filter(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    return discoverable_profiles_filter_errors()
