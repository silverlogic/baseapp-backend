import enum
from collections.abc import Callable
from typing import Any

import strawberry
import strawberry_django
from django.conf import settings
from easy_thumbnails.engine import NoSourceGenerator
from easy_thumbnails.exceptions import InvalidImageFormatError
from easy_thumbnails.files import get_thumbnailer
from strawberry.types import Info

from baseapp_core.graphql.fields import (
    _CACHE_MISS,
    FAILED_THUMBNAIL_CACHE_TIMEOUT,
    THUMBNAIL_CACHE_KEY_VERSION,
    cache,
)
from baseapp_core.graphql.translation import language_enum_name

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
    """Same contract (and cache keys) as `baseapp_core.graphql.ThumbnailField`."""
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
