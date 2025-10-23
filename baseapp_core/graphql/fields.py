import graphene
from django.apps import apps
from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from easy_thumbnails.files import get_thumbnailer

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None


def get_file_object_type():
    if apps.is_installed("baseapp.files"):
        import swapper

        File = swapper.load_model("baseapp_files", "File")
        FileObjectType = File.get_graphql_object_type()
    else:

        class FileObjectType(graphene.ObjectType):
            url = graphene.String(required=True)
            # contentType = graphene.String()
            # bytes = graphene.Int()

            class Meta:
                name = "File"

    return FileObjectType


class ThumbnailField(graphene.Field):
    def __init__(self, type=get_file_object_type, **kwargs):
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
        FileObjectType = get_file_object_type()

        def built_thumbnail(instance, info, width, height, **kwargs):
            instance = resolver(instance, info, **kwargs)

            if not instance:
                return None

            if cache:
                cache_key = self._get_cache_key(instance, width, height)
                value_from_cache = cache.get(cache_key)
                if value_from_cache:
                    return FileObjectType(url=value_from_cache)

            thumbnailer = get_thumbnailer(instance)
            url = thumbnailer.get_thumbnail({"size": (width, height)}).url
            absolute_url = info.context.build_absolute_uri(url)

            if cache:
                cache.set(cache_key, absolute_url, timeout=None)

            return FileObjectType(url=absolute_url)

        return built_thumbnail

    def _get_cache_key(self, instance, width, height):
        return f"et:thumbnail:{instance.url}:{width}:{height}"
