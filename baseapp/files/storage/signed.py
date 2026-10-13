from django.core.files.storage import FileSystemStorage

from ..tokens import FileDownloadToken


class SignedFileSystemStorage(FileSystemStorage):
    """
    Local private storage: files are never served from ``MEDIA_URL``, ``url()`` returns
    a link to ``FileDownloadViewSet`` that expires after ``BASEAPP_FILES_SIGNED_URL_MAX_AGE``.

    The local counterpart of a private S3 bucket with ``querystring_auth``, for
    development and deployments without S3. Point ``location`` outside any publicly
    served directory.
    """

    def url(self, name: str | None) -> str:
        return f"/v1/files/download/{FileDownloadToken.mint(name)}"
