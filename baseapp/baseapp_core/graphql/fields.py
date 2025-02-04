import graphene
from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from easy_thumbnails.files import get_thumbnailer

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None


class File(graphene.ObjectType):
    url = graphene.String(required=True)
    # contentType = graphene.String()
    # bytes = graphene.Int()


class ThumbnailField(graphene.Field):
    def __init__(self, type=File, **kwargs):
        kwargs.update(
            {
                "args": {
                    "width": graphene.Argument(graphene.Int, required=True),
                    "height": graphene.Argument(graphene.Int, required=True),
                }
            }
        )
        return super(ThumbnailField, self).__init__(type, **kwargs)

    def get_resolver(self, parent_resolver):
        resolver = self.resolver or parent_resolver

        def built_thumbnail(instance, info, width, height, **kwargs):
            instance = resolver(instance, info, **kwargs)

            if not instance:
                return None

            if cache:
                cache_key = self._get_cache_key(instance, width, height)
                value_from_cache = cache.get(cache_key)
                if value_from_cache:
                    return File(url=value_from_cache)

            thumbnailer = get_thumbnailer(instance)
            url = thumbnailer.get_thumbnail({"size": (width, height)}).url
            absolute_url = info.context.build_absolute_uri(url)

            if cache:
                cache.set(cache_key, absolute_url, timeout=None)

            return File(url=absolute_url)

        return built_thumbnail

    def _get_cache_key(self, instance, width, height):
        return f"et:thumbnail:{instance.url}:{width}:{height}"
