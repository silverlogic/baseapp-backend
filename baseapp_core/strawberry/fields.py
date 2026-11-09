import enum
from collections.abc import Callable
from typing import Any

import strawberry
import strawberry_django
from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from easy_thumbnails.engine import NoSourceGenerator
from easy_thumbnails.exceptions import InvalidImageFormatError
from easy_thumbnails.files import get_thumbnailer
from strawberry.types import Info

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None

# A missing or unreadable source is cached for a short while only, so a restored file recovers.
FAILED_THUMBNAIL_CACHE_TIMEOUT = 60 * 5
# Bump when the meaning of a cached value changes (v1 cached failures as a never-served None).
THUMBNAIL_CACHE_KEY_VERSION = "v2"
_CACHE_MISS = object()


def language_enum_name(code: str) -> str:
    """GraphQL enum members can't contain "-": "pt-br" becomes "pt_br" (the value stays "pt-br")."""
    return code.replace("-", "_")


Languages = strawberry.enum(
    enum.Enum("Languages", {language_enum_name(code): code for code, _ in settings.LANGUAGES}),
    name="Languages",
    description="Languages available",
)


@strawberry.interface(name="FileInterface")
class FileInterface:
    url: str | None


@strawberry.type(name="Thumbnail")
class Thumbnail(FileInterface):
    pass


def build_thumbnail_url(file: Any, info: Info, width: int, height: int) -> str | None:
    """Absolute URL of a `width`x`height` thumbnail of `file`, or None when it can't be read.

    Results are cached: a URL indefinitely, a failure for `FAILED_THUMBNAIL_CACHE_TIMEOUT`.
    """
    if not file:
        return None
    cache_key = f"et:thumbnail:{THUMBNAIL_CACHE_KEY_VERSION}:{file.url}:{width}:{height}"
    if cache:
        cached = cache.get(cache_key, _CACHE_MISS)
        if cached is not _CACHE_MISS:
            return cached
    try:
        url = get_thumbnailer(file).get_thumbnail({"size": (width, height)}).url
        absolute_url = info.context.build_absolute_uri(url)
    except (NoSourceGenerator, InvalidImageFormatError):
        absolute_url = None
    if cache:
        cache.set(
            cache_key,
            absolute_url,
            timeout=None if absolute_url else FAILED_THUMBNAIL_CACHE_TIMEOUT,
        )
    return absolute_url


def thumbnail_field(
    source: str | Callable[[Any], Any] | None = None,
    *,
    only: list[str] | None = None,
    **kwargs: Any,
) -> Any:
    """`field(width: Int!, height: Int!): String` resolving a thumbnail of an image field.

    `source` is the model attribute (defaults to the field name) or a callable on the instance.
    """

    def resolver(root: Any, info: Info, width: int, height: int) -> str | None:
        attr = source or info.python_name
        file = attr(root) if callable(attr) else getattr(root, attr, None)
        return build_thumbnail_url(file, info, width, height)

    if only is None and isinstance(source, str):
        only = [source]
    return strawberry_django.field(resolver=resolver, only=only, **kwargs)
