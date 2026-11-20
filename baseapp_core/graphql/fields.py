from collections.abc import Callable

import graphene
from django.apps import apps
from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from easy_thumbnails.engine import NoSourceGenerator
from easy_thumbnails.exceptions import InvalidImageFormatError
from easy_thumbnails.files import get_thumbnailer

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None

# A missing or unreadable source is cached for a short while only, so a restored file recovers.
FAILED_THUMBNAIL_CACHE_TIMEOUT = 60 * 5
# Bump this when the meaning of a cached value changes. v1 stored ``None`` for a failed thumbnail
# with no expiry but never served it, so those entries must not be read as hits now that ``None``
# is a valid cached result.
THUMBNAIL_CACHE_KEY_VERSION = "v2"
_CACHE_MISS = object()


class FileInterface(graphene.Interface):
    url = graphene.String()

    class Meta:
        name = "FileInterface"


class ThumbnailObjectType(graphene.ObjectType):
    class Meta:
        name = "Thumbnail"
        interfaces = (FileInterface,)


def get_file_object_type():
    if apps.is_installed("baseapp.files"):
        import swapper

        File = swapper.load_model("baseapp_files", "File")
        FileObjectType = File.get_graphql_object_type()
    else:

        class FileObjectType(graphene.ObjectType):
            class Meta:
                interfaces = (FileInterface,)
                name = "File"

    return FileObjectType


class ThumbnailField(graphene.Field):
    def __init__(self, type=graphene.String, **kwargs) -> None:
        kwargs.update(
            {
                "args": {
                    "width": graphene.Argument(graphene.Int, required=True),
                    "height": graphene.Argument(graphene.Int, required=True),
                }
            }
        )
        super(ThumbnailField, self).__init__(type, **kwargs)

    def get_resolver(self, parent_resolver) -> Callable:
        """Wrap the file resolver so the field resolves to a thumbnail URL of the requested size."""
        resolver = self.resolver or parent_resolver

        def built_thumbnail(instance, info, width, height, **kwargs) -> str | None:
            """Return the absolute thumbnail URL, or ``None`` when the source can't be thumbnailed.

            Results are cached: a URL indefinitely, a failure for ``FAILED_THUMBNAIL_CACHE_TIMEOUT``.
            """
            instance = resolver(instance, info, **kwargs)

            if not instance:
                return None

            if cache:
                cache_key = self._get_cache_key(instance, width, height)
                value_from_cache = cache.get(cache_key, _CACHE_MISS)
                if value_from_cache is not _CACHE_MISS:
                    return value_from_cache

            thumbnailer = get_thumbnailer(instance)
            try:
                url = thumbnailer.get_thumbnail({"size": (width, height)}).url
                absolute_url = info.context.build_absolute_uri(url)
            except (NoSourceGenerator, InvalidImageFormatError):
                # The source can't be read as an image (e.g. the file is missing from storage),
                # so the thumbnail resolves to null instead of failing the whole query.
                absolute_url = None

            if cache:
                timeout = None if absolute_url else FAILED_THUMBNAIL_CACHE_TIMEOUT
                cache.set(cache_key, absolute_url, timeout=timeout)

            return absolute_url

        return built_thumbnail

    def _get_cache_key(self, instance, width, height) -> str:
        """Build the cache key for one file at one size, namespaced by the cache-value version."""
        return f"et:thumbnail:{THUMBNAIL_CACHE_KEY_VERSION}:{instance.url}:{width}:{height}"
