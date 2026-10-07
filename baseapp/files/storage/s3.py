import posixpath
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.storage import Storage, default_storage
from django.utils.crypto import salted_hmac

from .base import BaseUploadHandler

S3_KEY_SALT = "baseapp.files.storage.s3.S3MultipartUploadHandler"


class S3MultipartUploadHandler(BaseUploadHandler):
    """Production S3 multipart upload with presigned URLs."""

    def __init__(self, storage: Optional[Storage] = None) -> None:
        # Reuse the configured django-storages backend instead of building a bare boto3
        # client, so endpoint (e.g. DigitalOcean Spaces), credentials, signature version,
        # addressing style, bucket, location prefix and ACL all match what
        # `FileField.url` and the rest of the project expect.
        self.storage = storage or default_storage
        self.s3_client = self.storage.connection.meta.client
        self.bucket = self.storage.bucket_name
        self.url_expiration = getattr(settings, "FILE_UPLOAD_PRESIGNED_URL_EXPIRATION", 3600)

    def supports_multipart(self) -> bool:
        return True

    def initiate_upload(self, file_obj, num_parts: int, part_size: int) -> Dict[str, Any]:
        """Initiate S3 multipart upload and generate presigned URLs."""

        # Validate constraints
        if num_parts > 10000:
            raise ValueError("S3 supports maximum 10,000 parts")
        if num_parts > 1 and part_size < 5 * 1024 * 1024:  # 5MB minimum
            raise ValueError("S3 requires minimum 5MB per part (except last)")

        # Get the S3 key for this file
        key = self._get_s3_key(file_obj)

        extra_args = {}
        default_acl = getattr(self.storage, "default_acl", None)
        if default_acl:
            extra_args["ACL"] = default_acl

        # Initiate multipart upload
        response = self.s3_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            ContentType=file_obj.file_content_type or "application/octet-stream",
            Metadata={
                "original_filename": file_obj.file_name or "",
                "created_by": str(file_obj.created_by_id) if file_obj.created_by_id else "",
            },
            **extra_args,
        )

        upload_id = response["UploadId"]

        # Generate presigned URLs for each part
        presigned_urls = []
        for part_num in range(1, num_parts + 1):
            url = self.s3_client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_num,
                },
                ExpiresIn=self.url_expiration,
            )
            presigned_urls.append(
                {
                    "part_number": part_num,
                    "url": url,
                }
            )

        return {
            "upload_id": upload_id,
            "presigned_urls": presigned_urls,
            "expires_in": self.url_expiration,
        }

    def complete_upload(self, file_obj, upload_id: str, parts: List[Dict]) -> str:
        """Complete S3 multipart upload."""

        key = self._get_s3_key(file_obj)

        # Format parts for S3 API
        multipart_upload = {
            "Parts": [
                {
                    "PartNumber": part["part_number"],
                    "ETag": part["etag"],
                }
                for part in sorted(parts, key=lambda x: x["part_number"])
            ]
        }

        # Complete the upload
        self.s3_client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload=multipart_upload,
        )

        # Return the storage name (without the storage `location` prefix); FileField
        # resolves it back to the S3 key and URL through the same storage.
        return self._get_file_name(file_obj)

    def abort_upload(self, file_obj, upload_id: str) -> None:
        """Abort S3 multipart upload and cleanup parts."""
        key = self._get_s3_key(file_obj)

        try:
            self.s3_client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
            )
        except ClientError as e:
            # Log but don't fail if already aborted/completed
            if e.response["Error"]["Code"] != "NoSuchUpload":
                raise

    def get_file_url(self, file_obj) -> Optional[str]:
        """Get the S3 URL for the file, or None if the file isn't stored yet."""
        if file_obj.file:
            return file_obj.file.url
        return None

    def _get_file_name(self, file_obj) -> str:
        """
        Storage name for ``file_obj``, stable across initiate, complete and abort.

        Initiate, complete and abort run in separate requests and the S3 key is not persisted,
        so it must be derived deterministically. An HMAC of the file's pk and creation time
        keeps it stable per file while staying unguessable for public-read buckets.
        """
        ext = (file_obj.file_name or "file").split(".")[-1]
        digest = salted_hmac(
            S3_KEY_SALT,
            f"{file_obj.pk}:{file_obj.created.isoformat()}",
            algorithm="sha256",
        ).hexdigest()[:32]
        return posixpath.join("files", f"{digest}.{ext}")

    def _get_s3_key(self, file_obj) -> str:
        """Full S3 object key, including the storage's `location` prefix."""
        location = (getattr(self.storage, "location", "") or "").strip("/")
        name = self._get_file_name(file_obj)
        return posixpath.join(location, name) if location else name
