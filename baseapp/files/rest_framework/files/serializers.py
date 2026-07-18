import swapper
from rest_framework import serializers

from baseapp_core.rest_framework.serializers import ModelSerializer

File = swapper.load_model("baseapp_files", "File")


class FileSerializer(ModelSerializer):
    """Standard file serializer for CRUD operations."""

    # Use public_id instead of primary key
    id = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    relay_id = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)

    # Parent DocumentId public_id
    parent_id = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            "id",
            "relay_id",
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
            "parent_id",
        ]
        read_only_fields = [
            "id",
            "relay_id",
            "upload_status",
            "created_by",
            "created",
            "modified",
            "file_size",
            "parent_id",
        ]

    def get_id(self, obj):
        """Get public_id instead of primary key."""
        return obj.public_id

    def get_url(self, obj):
        """Get file URL if upload completed."""
        if obj.upload_status == "completed" and obj.file:
            request = self.context.get("request")
            url = obj.file.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return None

    def get_relay_id(self, obj):
        """Get GraphQL relay ID for the file."""
        return obj.relay_id

    def get_parent_id(self, obj):
        """Get parent DocumentId public_id."""
        if obj.parent:
            return obj.parent.public_id
        return None
