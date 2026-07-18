import logging

import swapper
from django.core import signing
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ...services.upload_service import UploadService

logger = logging.getLogger(__name__)

File = swapper.load_model("baseapp_files", "File")


class PresignedUploadViewSet(viewsets.GenericViewSet):
    """
    ViewSet for handling presigned upload URLs (local storage fallback).

    This ViewSet does NOT use session authentication or CSRF protection.
    Instead, it validates signed tokens embedded in the URL.

    Endpoints:
        PUT /v1/files/presigned-uploads/{file_id}/upload-part/{part_number}/?token=...
    """

    queryset = File.objects.all()
    permission_classes = [AllowAny]  # Authentication via signed token
    authentication_classes = []  # No authentication classes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upload_service = UploadService()

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to disable CSRF protection."""
        return super().dispatch(request, *args, **kwargs)

    def perform_authentication(self, request):
        """
        Skip DRF's authentication process entirely.
        Authentication is handled via signed tokens in the URL.
        """
        pass

    @action(detail=True, methods=["put"], url_path="upload-part/(?P<part_number>[0-9]+)")
    def upload_part(self, request, pk=None, part_number=None):
        """
        Upload a single part using a presigned URL.

        PUT /v1/files/presigned-uploads/{file_id}/upload-part/{part_number}/?token=<signed_token>

        Body: raw binary data of the part

        Returns:
            {
                "part_number": 1,
                "etag": "abc123..."
            }
        """
        # Get and validate the signed token
        token = request.query_params.get("token")
        if not token:
            return Response(
                {"error": _("Missing token parameter")},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            # Verify the token (max age: 1 hour)
            token_data = signing.loads(token, max_age=3600)

            # Validate token matches request
            if str(token_data.get("file_id")) != str(pk) or str(
                token_data.get("part_number")
            ) != str(part_number):
                return Response(
                    {"error": _("Invalid token for this file/part")},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except signing.SignatureExpired:
            return Response(
                {"error": _("Token has expired")},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except signing.BadSignature:
            return Response(
                {"error": _("Invalid token signature")},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Get the file object
        try:
            file_obj = File.objects.get(id=pk)
        except File.DoesNotExist:
            return Response(
                {"error": _("File not found")},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Bind the token to the current upload session: a token minted for a
        # previous initiation (different upload_id) must not upload into a new one.
        if str(token_data.get("upload_id")) != str(file_obj.upload_id):
            return Response(
                {"error": _("Token does not match the current upload session")},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Validate state
        if file_obj.upload_status not in [File.UploadStatus.PENDING, File.UploadStatus.UPLOADING]:
            return Response(
                {
                    "error": _("Cannot upload parts in status: %(status)s")
                    % {"status": file_obj.upload_status}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only the local handler stores parts through this endpoint; S3 uploads
        # go straight to S3, so its handler has no upload_part.
        if not hasattr(self.upload_service.handler, "upload_part"):
            return Response(
                {"error": _("The active storage backend does not support presigned part uploads")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            part_number = int(part_number)

            # Validate part number
            if part_number < 1 or part_number > file_obj.total_parts:
                return Response(
                    {
                        "error": _("Invalid part number. Must be between 1 and %(total)s")
                        % {"total": file_obj.total_parts}
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the raw binary data from request
            data = request.body

            # Upload the part using the storage handler
            etag = self.upload_service.handler.upload_part(
                upload_id=file_obj.upload_id,
                part_number=part_number,
                data=data,
            )

            # Return response with ETag header (S3-compatible)
            response = Response(
                {"part_number": part_number, "etag": etag},
                status=status.HTTP_200_OK,
            )
            response["Access-Control-Expose-Headers"] = "*"
            response["ETag"] = etag
            return response

        except ValueError:
            logger.warning("Upload part rejected", exc_info=True)
            raise ValidationError([_("Invalid upload part request.")]) from None
        except Exception:
            logger.exception("Failed to upload part")
            raise ValidationError([_("Failed to upload part.")]) from None
