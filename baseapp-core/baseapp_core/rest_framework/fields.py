from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from drf_extra_fields.fields import Base64ImageField
from easy_thumbnails.files import get_thumbnailer

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None


class ThumbnailImageField(Base64ImageField):
    def __init__(self, *args, **kwargs):
        self.sizes = kwargs.pop("sizes", {})
        super(ThumbnailImageField, self).__init__(*args, **kwargs)

    def _get_cache_key(self, value):
        sizes = []
        for name, size in self.sizes.items():
            size_string = "-".join(map(str, size))
            sizes.append(f"{name}-{size_string}")
        sizes_string = "_".join(sizes)
        return f"et:thumbnail:{value.url}:{sizes_string}"

    def to_representation(self, value):
        if not value:
            return None

        if not getattr(value, "url", None):
            # If the file has not been saved it may not have a URL.
            return None

        has_sizes = len(self.sizes.keys()) > 0

        if has_sizes and cache:
            cache_key = self._get_cache_key(value)
            value_from_cache = cache.get(cache_key)
            if value_from_cache:
                return value_from_cache

        url = value.url
        request = self.context.get("request", None)
        if request is not None:
            url = request.build_absolute_uri(url)

        sizes = {"full_size": url}

        if has_sizes:
            thumbnailer = get_thumbnailer(value)
            for name, size in self.sizes.items():
                url = thumbnailer.get_thumbnail({"size": size}).url
                if request is not None:
                    url = request.build_absolute_uri(url)
                sizes[name] = url

            if cache:
                cache.set(cache_key, sizes, timeout=None)

        return sizes
