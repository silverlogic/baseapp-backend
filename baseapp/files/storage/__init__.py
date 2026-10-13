from typing import Optional

from django.conf import settings
from django.core.files.storage import Storage, storages
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.functional import LazyObject, empty

from .base import BaseUploadHandler

DEFAULT_FILES_STORAGE_ALIAS = "default"


class FilesStorage(LazyObject):
    """
    The storage that holds uploaded files: the ``STORAGES`` alias named by
    ``BASEAPP_FILES_STORAGE`` (``"default"`` unless a project sets another one, e.g. a
    private bucket).

    Lazy, like ``default_storage``, so the alias is read when first used rather than at
    import, and is re-read after the setting changes (see ``_reset_files_storage``).
    """

    def _setup(self) -> None:
        alias = getattr(settings, "BASEAPP_FILES_STORAGE", DEFAULT_FILES_STORAGE_ALIAS)
        self._wrapped = storages[alias]


files_storage = FilesStorage()


def get_files_storage() -> Storage:
    """``File.file``'s storage. A callable, so migrations record a reference to it."""
    return files_storage


@receiver(setting_changed)
def _reset_files_storage(*, setting: str, **kwargs) -> None:
    # Django's own receiver rebuilds `storages` when STORAGES changes.
    if setting in ("BASEAPP_FILES_STORAGE", "STORAGES"):
        files_storage._wrapped = empty


def _is_s3_storage(storage: Storage) -> bool:
    """
    Whether ``storage`` is a django-storages S3 backend, including subclasses such as
    ``s3_folder_storage.s3.DefaultStorage``.

    ``files_storage`` is a LazyObject, which proxies ``__class__`` to the wrapped backend,
    so ``isinstance`` sees the real storage class.
    """
    try:
        from storages.backends.s3boto3 import S3Boto3Storage
    except ImportError:
        return False
    return isinstance(storage, S3Boto3Storage)


def files_storage_is_private(storage: Optional[Storage] = None) -> bool:
    """
    Whether files are private: their storage only hands out signed, expiring URLs.

    That is an S3 storage with ``querystring_auth`` on (django-storages presigns
    ``url()``), or ``SignedFileSystemStorage``. Derived from the storage instead of a
    separate flag, so a "private" setting can never be paired with a public bucket.
    """
    from .signed import SignedFileSystemStorage

    storage = files_storage if storage is None else storage
    if isinstance(storage, SignedFileSystemStorage):
        return True
    return _is_s3_storage(storage) and bool(getattr(storage, "querystring_auth", False))


def get_upload_handler(storage: Optional[Storage] = None) -> BaseUploadHandler:
    """
    Factory to get the upload handler for the files storage: S3 multipart for an S3
    backend, the local presigned fallback otherwise.
    """
    storage = files_storage if storage is None else storage
    if _is_s3_storage(storage):
        from .s3 import S3MultipartUploadHandler

        return S3MultipartUploadHandler(storage=storage)

    from .local import LocalUploadHandler

    return LocalUploadHandler(storage=storage)
