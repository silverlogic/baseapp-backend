import swapper
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from baseapp_core.rest_framework.decorators import action
from baseapp_profiles.rest_framework import CurrentProfileMixin

from ..uploads.permissions import IsOwnerOrReadOnly
from ..uploads.serializers import SetParentSerializer
from .serializers import FileSerializer

File = swapper.load_model("baseapp_files", "File")


class FilesViewSet(
    CurrentProfileMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for file CRUD operations.

    Endpoints:
        GET /v1/files/ - List files
        GET /v1/files/{id} - Retrieve file
        PATCH /v1/files/{id} - Update file metadata
        DELETE /v1/files/{id} - Delete file
        POST /v1/files/{id}/set-parent - Set parent after upload
    """

    serializer_class = FileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        """Filter files based on user and query params."""
        qs = File.objects.all()

        # Only show completed files by default
        status_filter = self.request.query_params.get("status", File.UploadStatus.COMPLETED)
        if status_filter:
            qs = qs.filter(upload_status=status_filter)

        # Filter by parent
        parent_ct = self.request.query_params.get("parent_content_type")
        parent_id = self.request.query_params.get("parent_object_id")
        if parent_ct and parent_id:
            qs = qs.filter(
                parent_content_type__model=parent_ct.split(".")[-1],
                parent_object_id=parent_id,
            )

        # Filter by owner (users can see their own files)
        if not self.request.user.is_staff:
            qs = qs.filter(created_by=self.request.user)

        return qs.select_related("created_by").order_by("-created")

    @action(detail=True, methods=["post"], serializer_class=SetParentSerializer)
    def set_parent(self, request, pk=None):
        """
        Set parent for a standalone file.

        POST /v1/files/{id}/set-parent
        {
            "parent_content_type": "testapp.post",
            "parent_object_id": 123
        }
        """
        file_obj = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj.parent_content_type_id = serializer.validated_data["parent_content_type_id"]
        file_obj.parent_object_id = serializer.validated_data["parent_object_id"]
        file_obj.save()

        return Response(
            FileSerializer(file_obj, context={"request": request}).data, status=status.HTTP_200_OK
        )
