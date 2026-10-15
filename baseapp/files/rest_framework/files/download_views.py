import posixpath

import swapper
from django.core import signing
from django.http import FileResponse
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny

from ...storage import get_files_storage
from ...tokens import FileDownloadToken

File = swapper.load_model("baseapp_files", "File")


class FileDownloadViewSet(viewsets.GenericViewSet):
    """
    Serves the expiring links ``SignedFileSystemStorage.url`` hands out.

    The signed token in the URL is the only credential, like a presigned S3 URL: whoever
    holds the link may download the file until it expires.

    Always served as an attachment with ``nosniff``: rendered inline on the app's own
    domain, an uploaded HTML or SVG file would run script there.

    Endpoints:
        GET /v1/files/download/{token}
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "token"
    lookup_value_regex = r"[^/]+"

    def perform_authentication(self, request) -> None:
        """Skip DRF authentication: the signed token authorizes the download."""

    def retrieve(self, request, token: str | None = None) -> FileResponse:
        try:
            name = FileDownloadToken.verify(token)
        except signing.SignatureExpired:
            raise PermissionDenied(_("This download link has expired.")) from None
        except signing.BadSignature:
            raise PermissionDenied(_("Invalid download link.")) from None

        storage = get_files_storage()
        if not storage.exists(name):
            raise NotFound(_("File not found"))

        file_obj = File.objects.filter(file=name).only("file_name", "file_content_type").first()
        response = FileResponse(
            storage.open(name, "rb"),
            as_attachment=True,
            filename=(file_obj and file_obj.file_name) or posixpath.basename(name),
            content_type=(file_obj and file_obj.file_content_type) or None,
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
