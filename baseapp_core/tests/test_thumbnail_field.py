from unittest.mock import MagicMock

from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.db import models
from django.db.models.fields.files import FieldFile

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
