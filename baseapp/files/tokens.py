from typing import Any, Dict

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
