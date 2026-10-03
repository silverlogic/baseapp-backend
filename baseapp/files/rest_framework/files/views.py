import swapper
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from baseapp_core.models import DocumentId
from baseapp_core.rest_framework.decorators import action
from baseapp_profiles.rest_framework import CurrentProfileMixin

from ..uploads.permissions import IsOwnerOrReadOnly
from ..uploads.serializers import SetParentSerializer
from ..utils import enforce_can_attach_to_parent
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
        GET /v1/files/{public_id} - Retrieve file
        PATCH /v1/files/{public_id} - Update file metadata
        DELETE /v1/files/{public_id} - Delete file
        POST /v1/files/{public_id}/set-parent - Set parent after upload
    """

    serializer_class = FileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    lookup_field = "pk"
    lookup_url_kwarg = "pk"

    def get_object(self):
        """Look up file by public_id instead of primary key."""
        from rest_framework.exceptions import NotFound

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        public_id = self.kwargs[lookup_url_kwarg]

        obj = File.get_by_public_id(public_id)
        if obj is None:
            raise NotFound(_("File not found"))

        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        """Filter files based on user and query params."""
        qs = File.objects.all()

        # Only show completed files by default. Use `is not None` so an empty
        # `?status=` doesn't fall through and expose files in every state.
        status_filter = self.request.query_params.get("status", File.UploadStatus.COMPLETED)
        if status_filter is not None and status_filter != "":
            qs = qs.filter(upload_status=status_filter)

        # Filter by parent using DocumentId public_id
        parent_id = self.request.query_params.get("parent_id")
        if parent_id:
            try:
                document_id = DocumentId.objects.get(public_id=parent_id)
                qs = qs.filter(parent=document_id)
            except DocumentId.DoesNotExist:
                qs = qs.none()

        # Filter by owner (users can see their own files)
        if not self.request.user.is_staff:
            qs = qs.filter(created_by=self.request.user)

        return qs.select_related("created_by", "parent__content_type").order_by("-created")

    @action(detail=True, methods=["post"], serializer_class=SetParentSerializer)
    def set_parent(self, request, pk=None):
        """
        Set parent for a standalone file.

        POST /v1/files/{id}/set-parent
        {
            "parent_id": "uuid-of-document-id"
        }
        """
        file_obj = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        parent_pk = serializer.validated_data["parent_id"]
        # Enforce target-level authorization, mirroring fileAttachToTarget.
        enforce_can_attach_to_parent(request.user, parent_pk)

        file_obj.parent_id = parent_pk
        file_obj.save()

        return Response(
            FileSerializer(file_obj, context={"request": request}).data, status=status.HTTP_200_OK
        )
