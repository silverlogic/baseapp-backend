from django.core.files.storage import default_storage

from .base import BaseUploadHandler


def _is_s3_storage(storage) -> bool:
    """
    Whether ``storage`` is a django-storages S3 backend, including subclasses such as
    ``s3_folder_storage.s3.DefaultStorage``.

    ``default_storage`` is a LazyObject, which proxies ``__class__`` to the wrapped backend,
    so ``isinstance`` sees the real storage class.
    """
    try:
        from storages.backends.s3boto3 import S3Boto3Storage
    except ImportError:
        return False
    return isinstance(storage, S3Boto3Storage)


def get_upload_handler() -> BaseUploadHandler:
    """
    Factory to get appropriate upload handler based on storage backend.
    """
    if _is_s3_storage(default_storage):
        from .s3 import S3MultipartUploadHandler

        return S3MultipartUploadHandler()

    from .local import LocalUploadHandler

    return LocalUploadHandler()
