import graphene
from django.apps import apps
from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from easy_thumbnails.engine import NoSourceGenerator
from easy_thumbnails.files import get_thumbnailer

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None


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
    def __init__(self, type=graphene.String, **kwargs):
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
                    return value_from_cache

            thumbnailer = get_thumbnailer(instance)
            try:
                url = thumbnailer.get_thumbnail({"size": (width, height)}).url
                absolute_url = info.context.build_absolute_uri(url)
            except NoSourceGenerator:
                absolute_url = None

            if cache:
                cache.set(cache_key, absolute_url, timeout=None)

            return absolute_url

        return built_thumbnail

    def _get_cache_key(self, instance, width, height):
        return f"et:thumbnail:{instance.url}:{width}:{height}"
