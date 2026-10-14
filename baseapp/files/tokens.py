from typing import Any, Dict, Iterable, Set

from django.conf import settings
from django.core import signing
from django.utils.translation import gettext_lazy as _


class PresignedUploadTokenError(Exception):
    """
    Raised when a presigned upload token is missing, expired, or does not match
    the request it was presented with.

    `message` is a client-safe, translated string: it describes only which check
    failed, never any detail of the signed payload.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PresignedUploadToken:
    """
    Mints and verifies the signed tokens that authenticate part uploads against
    the local-storage presigned fallback.

    `LocalUploadHandler` embeds a token in each presigned URL it hands out, and
    `PresignedUploadViewSet` verifies it — that endpoint has no session auth or
    CSRF, so the token is the only thing authorizing the write. The S3 handler
    issues real presigned URLs and does not use this.
    """

    SALT = "baseapp_files.presigned_upload"

    @classmethod
    def max_age(cls) -> int:
        """Token lifetime in seconds; shared with the S3 handler's URL expiration."""
        return getattr(settings, "FILE_UPLOAD_PRESIGNED_URL_EXPIRATION", 3600)

    @classmethod
    def mint(cls, *, file_id: Any, part_number: int, upload_id: str) -> str:
        """Sign a token authorizing one part of one upload session."""
        return signing.dumps(
            {
                "file_id": file_id,
                "part_number": part_number,
                "upload_id": upload_id,
            },
            salt=cls.SALT,
        )

    @classmethod
    def verify(cls, token: str | None, *, file_id: Any, part_number: Any) -> Dict[str, Any]:
        """
        Validate `token` against the file and part it is being used for and
        return its payload.

        The payload's `upload_id` still has to be checked against the file's
        current upload session — see `check_upload_session`, which runs once the
        file has been loaded.

        Raises:
            PresignedUploadTokenError: token missing, expired, tampered with, or
                issued for a different file/part.
        """
        if not token:
            raise PresignedUploadTokenError(_("Missing token parameter"))

        try:
            token_data = signing.loads(token, max_age=cls.max_age(), salt=cls.SALT)
        except signing.SignatureExpired:
            raise PresignedUploadTokenError(_("Token has expired")) from None
        except signing.BadSignature:
            raise PresignedUploadTokenError(_("Invalid token signature")) from None

        if str(token_data.get("file_id")) != str(file_id) or str(
            token_data.get("part_number")
        ) != str(part_number):
            raise PresignedUploadTokenError(_("Invalid token for this file/part"))

        return token_data

    @staticmethod
    def check_upload_session(token_data: Dict[str, Any], upload_id: str) -> None:
        """
        Bind the token to the current upload session: one minted for a previous
        initiation (different `upload_id`) must not upload into a new one.

        Raises:
            PresignedUploadTokenError: token belongs to a different session.
        """
        if str(token_data.get("upload_id")) != str(upload_id):
            raise PresignedUploadTokenError(_("Token does not match the current upload session"))


class AnonymousUploadToken:
    """
    Proves an anonymous caller started an upload, since no user owns the file.

    Minted at initiation for anonymous callers and returned as ``upload_token``. The
    client sends it back to complete or abort the upload (``X-File-Upload-Token``) and to
    attach the file (``fileAttachToTarget``'s ``uploadTokens``); ``bind_upload_tokens``
    then lets ``FilesPermissionsBackend`` treat the holder as the file's owner.
    """

    SALT = "baseapp_files.anonymous_upload"
    HEADER = "HTTP_X_FILE_UPLOAD_TOKEN"

    @classmethod
    def max_age(cls) -> int:
        return getattr(settings, "BASEAPP_FILES_UPLOAD_TOKEN_MAX_AGE", 24 * 60 * 60)

    @classmethod
    def mint(cls, file_obj: Any) -> str:
        return signing.dumps({"file_id": file_obj.pk}, salt=cls.SALT)

    @classmethod
    def file_ids(cls, tokens: Iterable[str]) -> Set[Any]:
        """Ids of the files the valid tokens grant; invalid or expired ones are ignored."""
        file_ids = set()
        for token in tokens:
            try:
                data = signing.loads(token, max_age=cls.max_age(), salt=cls.SALT)
            except signing.BadSignature:
                continue
            file_ids.add(data.get("file_id"))
        return file_ids


def bind_upload_tokens(user: Any, tokens: Iterable[str] | str | None) -> None:
    """
    Record on ``user`` the files the given upload tokens grant, for the permission
    backend to read (as ``CurrentProfileMixin`` does with ``current_profile``).

    ``tokens`` may be a list or a comma-separated string, as sent in the header.
    """
    if not tokens:
        return
    if isinstance(tokens, str):
        tokens = [token.strip() for token in tokens.split(",")]
    file_ids = AnonymousUploadToken.file_ids(token for token in tokens if token)
    if file_ids:
        user.file_upload_tokens = getattr(user, "file_upload_tokens", set()) | file_ids


def bind_request_upload_tokens(request: Any) -> None:
    """
    Bind the ``X-File-Upload-Token`` header of ``request`` to its user, once per request,
    so an anonymous uploader can read its file through any API, not only the upload ones.
    """
    if getattr(request, "_baseapp_files_upload_tokens_bound", False):
        return
    request._baseapp_files_upload_tokens_bound = True
    bind_upload_tokens(request.user, getattr(request, "META", {}).get(AnonymousUploadToken.HEADER))


class FileDownloadToken:
    """Signs the expiring download links that ``SignedFileSystemStorage.url`` hands out."""

    SALT = "baseapp_files.download"

    @classmethod
    def max_age(cls) -> int:
        return getattr(settings, "BASEAPP_FILES_SIGNED_URL_MAX_AGE", 60 * 60)

    @classmethod
    def mint(cls, name: str) -> str:
        return signing.dumps({"name": name}, salt=cls.SALT)

    @classmethod
    def verify(cls, token: str) -> str:
        """
        Return the storage name ``token`` grants.

        Raises:
            signing.BadSignature: tampered with or expired (``SignatureExpired``).
        """
        return signing.loads(token, max_age=cls.max_age(), salt=cls.SALT)["name"]
