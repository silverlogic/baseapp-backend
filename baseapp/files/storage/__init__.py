from django.core.files.storage import default_storage


def get_upload_handler():
    """
    Factory to get appropriate upload handler based on storage backend.
    """
    storage_class = type(default_storage)

    # Check if using S3 storage
    if "S3Boto3Storage" in str(storage_class):
        from .s3 import S3MultipartUploadHandler

        return S3MultipartUploadHandler()
    else:
        from .local import LocalUploadHandler

        return LocalUploadHandler()
