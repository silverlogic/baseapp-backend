from typing import Any

from django.core.checks import CheckMessage, Error, Tags, Warning, register
from django.core.exceptions import FieldDoesNotExist
from django.core.files.storage import InvalidStorageError, Storage
from django.db import models

from ..storage import files_storage_is_private
from ..storage.alias import AliasStorage
from .registry import protected_files


def storage_name(storage: Storage) -> str:
    # `__class__` sees through LazyObject storages such as `files_storage`.
    return repr(storage) if isinstance(storage, AliasStorage) else storage.__class__.__name__


@register()
def check_protected_files(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    """Every registered protected file names a file field and a lookup field of its model."""
    errors = []
    for spec in protected_files:
        label = f"{spec.model._meta.label}.{spec.field}"
        try:
            field = spec.model._meta.get_field(spec.field)
        except FieldDoesNotExist:
            errors.append(
                Error(
                    f"Protected file {spec.key!r} names {label}, which does not exist.",
                    id="baseapp_files.E010",
                )
            )
            continue
        if not isinstance(field, models.FileField):
            errors.append(
                Error(
                    f"Protected file {spec.key!r} names {label}, which is not a FileField.",
                    id="baseapp_files.E011",
                )
            )
        if spec.lookup_field != "pk" and not spec.uses_public_id():
            try:
                spec.model._meta.get_field(spec.lookup_field)
            except FieldDoesNotExist:
                errors.append(
                    Error(
                        f"Protected file {spec.key!r}: lookup_field {spec.lookup_field!r} is not "
                        f"a field of {spec.model._meta.label}.",
                        id="baseapp_files.E012",
                    )
                )
    return errors


@register(Tags.security)
def check_protected_file_storage(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """
    Registering a field does not move its file: a field on public storage stays readable at
    its storage URL. Only storages that sign their URLs can be told apart, so this is a
    warning that projects whose web server denies the storage's URLs can silence.
    """
    warnings = []
    for spec in protected_files:
        try:
            field = spec.model._meta.get_field(spec.field)
        except FieldDoesNotExist:
            continue  # E010
        if not isinstance(field, models.FileField):
            continue  # E011
        try:
            private = files_storage_is_private(field.storage)
        except InvalidStorageError:
            private = False
        if not private:
            warnings.append(
                Warning(
                    f"Protected file {spec.key!r}: {spec.model._meta.label}.{spec.field} is on "
                    f"{storage_name(field.storage)}, which does not keep files private, so "
                    "anyone with its storage URL can still read them.",
                    hint="Put the field on private storage (S3 with querystring_auth, "
                    "SignedFileSystemStorage, or an AliasStorage naming one). If the web server "
                    "denies the storage's URLs, silence baseapp_files.W010.",
                    obj=spec.model,
                    id="baseapp_files.W010",
                )
            )
    return warnings
