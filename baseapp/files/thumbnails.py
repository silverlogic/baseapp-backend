from django.core.cache import cache
from django.db.models.fields.files import FieldFile
from easy_thumbnails.engine import NoSourceGenerator
from easy_thumbnails.exceptions import InvalidImageFormatError
from easy_thumbnails.files import get_thumbnailer

from .storage import get_wrapped_files_storage


def private_thumbnail_name(field_file: FieldFile, width: int, height: int) -> str | None:
    """
    Storage name of a ``width`` x ``height`` thumbnail of a private file, generated on first
    use into the files storage itself, so it is as private as the original and only ever
    reached through a signed URL. ``None`` when the file is not an image.

    Caches the name, never a URL: signed URLs expire.
    """
    cache_key = f"baseapp_files:thumbnail:{field_file.name}:{width}x{height}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None

    # easy-thumbnails mis-hashes a LazyObject it has to load itself; hand it the real storage.
    storage = get_wrapped_files_storage()
    thumbnailer = get_thumbnailer(field_file)
    thumbnailer.source_storage = storage
    thumbnailer.thumbnail_storage = storage
    try:
        name = thumbnailer.get_thumbnail({"size": (width, height)}).name
    except (NoSourceGenerator, InvalidImageFormatError):
        name = ""

    cache.set(cache_key, name, timeout=None)
    return name or None
