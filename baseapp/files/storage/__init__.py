from django.core.files.storage import default_storage


def get_upload_handler():
    """
    Factory to get appropriate upload handler based on storage backend.
    """
    # `default_storage` is a LazyObject: type() returns the wrapper class, so
    # use `__class__`, which LazyObject proxies to the wrapped backend, to
    # detect the real storage backend.
    storage_class_name = default_storage.__class__.__name__

    # Check if using S3 storage
    if "S3Boto3Storage" in storage_class_name:
        from .s3 import S3MultipartUploadHandler

        return S3MultipartUploadHandler()
    else:
        from .local import LocalUploadHandler

        return LocalUploadHandler()
