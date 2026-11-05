from unittest.mock import ANY, MagicMock

from django.core.cache.backends.locmem import LocMemCache
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.db import models
from django.db.models.fields.files import FieldFile

from baseapp_core.graphql import fields
from baseapp_core.graphql.fields import ThumbnailField


def test_thumbnail_of_file_missing_from_storage_resolves_to_none() -> None:
    # Regression for Sentry BASEAPP-BACKEND-TEMPLATE-G2: a file whose blob is gone from storage
    # raised InvalidImageFormatError and failed the whole GraphQL query.
    missing_file = FieldFile(instance=None, field=models.FileField(), name="files/missing.png")
    resolver = ThumbnailField().get_resolver(lambda instance, info, **kwargs: missing_file)
    info = MagicMock()

    assert resolver(None, info, width=48, height=48) is None
    info.context.build_absolute_uri.assert_not_called()


def test_thumbnail_of_file_that_is_not_an_image_resolves_to_none() -> None:
    # The file opens but no source generator can read it, so easy_thumbnails raises
    # NoSourceGenerator rather than InvalidImageFormatError.
    storage = InMemoryStorage()
    name = storage.save("files/not-an-image.png", ContentFile(b"not an image"))
    not_an_image = FieldFile(instance=None, field=models.FileField(storage=storage), name=name)
    resolver = ThumbnailField().get_resolver(lambda instance, info, **kwargs: not_an_image)
    info = MagicMock()

    assert resolver(None, info, width=48, height=48) is None
    info.context.build_absolute_uri.assert_not_called()


def test_thumbnail_failure_is_cached_briefly(monkeypatch) -> None:
    # A failed thumbnail is served from cache instead of hitting storage on every request,
    # but only for a short while so the thumbnail recovers once the file is restored.
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(fields, "cache", cache)
    get_thumbnailer = MagicMock()
    monkeypatch.setattr(fields, "get_thumbnailer", get_thumbnailer)
    missing_file = FieldFile(instance=None, field=models.FileField(), name="files/cached.png")
    resolver = ThumbnailField().get_resolver(lambda instance, info, **kwargs: missing_file)

    assert resolver(None, MagicMock(), width=48, height=48) is None
    get_thumbnailer.assert_not_called()

    cache.get.return_value = fields._CACHE_MISS
    get_thumbnailer.return_value.get_thumbnail.side_effect = fields.InvalidImageFormatError
    assert resolver(None, MagicMock(), width=48, height=48) is None
    cache.set.assert_called_once_with(
        ANY,
        None,
        timeout=fields.FAILED_THUMBNAIL_CACHE_TIMEOUT,
    )


def test_thumbnail_ignores_failures_cached_by_previous_versions(monkeypatch) -> None:
    # Before the cache-value version was introduced, a failed thumbnail was cached as None with
    # no expiry but treated as a miss. Those entries must stay invisible now that a cached None
    # is a hit, or a file replaced with a readable image would resolve to null forever.
    cache = LocMemCache("thumbnail-test", {})
    monkeypatch.setattr(fields, "cache", cache)
    get_thumbnailer = MagicMock()
    get_thumbnailer.return_value.get_thumbnail.return_value.url = "/media/thumb.png"
    monkeypatch.setattr(fields, "get_thumbnailer", get_thumbnailer)
    restored_file = FieldFile(instance=None, field=models.FileField(), name="files/restored.png")
    cache.set(f"et:thumbnail:{restored_file.url}:48:48", None, timeout=None)
    resolver = ThumbnailField().get_resolver(lambda instance, info, **kwargs: restored_file)
    info = MagicMock()
    info.context.build_absolute_uri.return_value = "http://testserver/media/thumb.png"

    assert resolver(None, info, width=48, height=48) == "http://testserver/media/thumb.png"
    get_thumbnailer.assert_called_once_with(restored_file)
    assert cache.get(f"et:thumbnail:v2:{restored_file.url}:48:48") == (
        "http://testserver/media/thumb.png"
    )
