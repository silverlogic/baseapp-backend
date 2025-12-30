import swapper
from rest_framework import serializers

from baseapp_core.rest_framework.serializers import ModelSerializer

File = swapper.load_model("baseapp_files", "File")


class FileSerializer(ModelSerializer):
    """Standard file serializer for CRUD operations."""

    url = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)

    class Meta:
        model = File
        fields = [
            "id",
            "file_name",
            "file_size",
            "file_content_type",
            "name",
            "description",
            "url",
            "upload_status",
            "created_by",
            "created_by_name",
            "created",
            "modified",
            "parent_content_type",
            "parent_object_id",
        ]
        read_only_fields = [
            "id",
            "upload_status",
            "created_by",
            "created",
            "modified",
            "file_size",
        ]

    def get_url(self, obj):
        """Get file URL if upload completed."""
        if obj.upload_status == "completed" and obj.file:
            request = self.context.get("request")
            url = obj.file.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return None
