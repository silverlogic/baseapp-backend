import swapper
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from baseapp_core.rest_framework.decorators import action
from baseapp_profiles.rest_framework import CurrentProfileMixin

from ...services.upload_service import UploadService
from .serializers import (
    CompleteUploadSerializer,
    InitiateUploadSerializer,
    UploadResponseSerializer,
)

File = swapper.load_model("baseapp_files", "File")


class FileUploadViewSet(CurrentProfileMixin, viewsets.GenericViewSet):
    """
    ViewSet for managing multipart file uploads.

    Endpoints:
        POST /v1/files/uploads/ - Initiate upload
        POST /v1/files/uploads/{id}/complete - Complete upload
        DELETE /v1/files/uploads/{id} - Abort upload

    Note: Part uploads for local storage use presigned URLs handled by PresignedUploadViewSet
    """

    queryset = File.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upload_service = UploadService()

    def get_serializer_class(self):
        if self.action == "create":
            return InitiateUploadSerializer
        elif self.action == "complete":
            return CompleteUploadSerializer
        return InitiateUploadSerializer

    def create(self, request):
        """
        Initiate a multipart upload.

        POST /v1/files/uploads/
        {
            "file_name": "large-video.mp4",
            "file_size": 104857600,
            "file_content_type": "video/mp4",
            "num_parts": 20,
            "part_size": 5242880,
            "parent_content_type": "testapp.post",  // optional
            "parent_object_id": 123  // optional
        }

        Returns presigned URLs for each part.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Get user's profile if available
            profile = request.user.current_profile

            file_obj, upload_data = self.upload_service.initiate_multipart_upload(
                user=request.user, profile=profile, **serializer.validated_data
            )

            # Prepare response
            response_data = {"file_obj": file_obj, **upload_data}

            response_serializer = UploadResponseSerializer(response_data)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            raise ValidationError(str(e))
        except Exception as e:
            raise ValidationError(f"Failed to initiate upload: {str(e)}")

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """
        Complete a multipart upload.

        POST /v1/files/uploads/{id}/complete
        {
            "parts": [
                {"part_number": 1, "etag": "abc123..."},
                {"part_number": 2, "etag": "def456..."},
                ...
            ]
        }
        """
        file_obj = self.get_object()

        # Check ownership
        if file_obj.created_by != request.user:
            return Response(
                {"error": "You don't have permission to complete this upload"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            completed_file = self.upload_service.complete_multipart_upload(
                file_id=file_obj.id, parts=serializer.validated_data["parts"]
            )

            from ..files.serializers import FileSerializer

            return Response(
                FileSerializer(completed_file, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            raise ValidationError(str(e))
        except Exception as e:
            raise ValidationError(f"Failed to complete upload: {str(e)}")

    def destroy(self, request, pk=None):
        """
        Abort a multipart upload.

        DELETE /v1/files/uploads/{id}
        """
        file_obj = self.get_object()

        # Check ownership
        if file_obj.created_by != request.user:
            return Response(
                {"error": "You don't have permission to abort this upload"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            self.upload_service.abort_multipart_upload(file_obj.id)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            raise ValidationError(f"Failed to abort upload: {str(e)}")
