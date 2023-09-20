from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

from baseapp_core.models import random_name_in

from .base import BaseUploadHandler


class S3MultipartUploadHandler(BaseUploadHandler):
    """Production S3 multipart upload with presigned URLs."""

    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
        )
        self.bucket = settings.AWS_STORAGE_BUCKET_NAME
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

        # Initiate multipart upload
        response = self.s3_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            ContentType=file_obj.file_content_type or "application/octet-stream",
            Metadata={
                "original_filename": file_obj.file_name or "",
                "created_by": str(file_obj.created_by_id) if file_obj.created_by_id else "",
            },
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

        # Return the file key (not full URL, FileField will handle that)
        return key

    def abort_upload(self, file_obj, upload_id: str):
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

    def get_file_url(self, file_obj) -> str:
        """Get the S3 URL for the file."""
        if file_obj.file:
            return file_obj.file.url
        return None

    def _get_s3_key(self, file_obj) -> str:
        """Generate S3 key from file object."""
        # Use the same upload_to logic from the FileField
        return random_name_in("files")(file_obj, file_obj.file_name or "file")
