"""Helpers for rendering user-facing text in a specific user's language.

Request-time code gets its language from ``LocaleMiddleware`` (``Accept-Language``),
but emails and other out-of-request work (Celery tasks, admin actions) run in the
process default language unless they activate the recipient's language explicitly.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from django.conf import settings
from django.utils import translation


def get_user_language(user: Any) -> str:
    """Return the language to render content for ``user`` (falls back to ``LANGUAGE_CODE``)."""
    return getattr(user, "preferred_language", None) or settings.LANGUAGE_CODE


@contextmanager
def user_language(user: Any) -> Iterator[None]:
    """Activate ``user``'s preferred language for the duration of the block."""
    with translation.override(get_user_language(user)):
        yield


def group_by_language(users: Iterable[Any]) -> dict[str, list[Any]]:
    """Bucket users by preferred language so a broadcast can be rendered once per language."""
    groups: dict[str, list[Any]] = {}
    for user in users:
        groups.setdefault(get_user_language(user), []).append(user)
    return groups
