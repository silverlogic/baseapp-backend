import swapper
from rest_framework import serializers

from baseapp_core.models import DocumentId

File = swapper.load_model("baseapp_files", "File")


class InitiateUploadSerializer(serializers.Serializer):
    """Serializer for initiating a multipart upload."""

    file_name = serializers.CharField(max_length=512)
    file_size = serializers.IntegerField(min_value=1)
    file_content_type = serializers.CharField(max_length=150)
    num_parts = serializers.IntegerField(min_value=1, max_value=10000)
    part_size = serializers.IntegerField(min_value=1)

    # Optional parent relationship via DocumentId public_id
    parent_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_parent_id(self, value):
        """Validate parent_id exists as a DocumentId public_id."""
        if not value:
            return None

        try:
            document_id = DocumentId.objects.get(public_id=value)
            return document_id.pk
        except DocumentId.DoesNotExist:
            raise serializers.ValidationError("Invalid parent_id: DocumentId not found")

    def validate(self, data):
        """Validate file size matches parts."""
        num_parts = data["num_parts"]
        part_size = data["part_size"]
        file_size = data["file_size"]

        min_size = (num_parts - 1) * part_size
        max_size = num_parts * part_size

        if file_size < min_size or file_size > max_size:
            raise serializers.ValidationError(
                f"File size {file_size} doesn't match {num_parts} parts of {part_size} bytes"
            )

        return data


class UploadResponseSerializer(serializers.Serializer):
    """Response serializer for initiated upload."""

    id = serializers.UUIDField(source="file_obj.public_id")
    relay_id = serializers.CharField(source="file_obj.relay_id", read_only=True)
    upload_id = serializers.CharField()
    presigned_urls = serializers.ListField()
    expires_in = serializers.IntegerField()
    upload_status = serializers.CharField(source="file_obj.upload_status")


class CompleteUploadSerializer(serializers.Serializer):
    """Serializer for completing a multipart upload."""

    parts = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )

    def validate_parts(self, value):
        """Validate parts structure."""
        for part in value:
            if "part_number" not in part or "etag" not in part:
                raise serializers.ValidationError("Each part must have 'part_number' and 'etag'")

            if not isinstance(part["part_number"], int) or part["part_number"] < 1:
                raise serializers.ValidationError("part_number must be a positive integer")

            if not isinstance(part["etag"], str) or not part["etag"]:
                raise serializers.ValidationError("etag must be a non-empty string")

        return value


class SetParentSerializer(serializers.Serializer):
    """Serializer for setting parent after upload."""

    parent_id = serializers.UUIDField()

    def validate_parent_id(self, value):
        """Validate parent_id exists as a DocumentId public_id."""
        try:
            document_id = DocumentId.objects.get(public_id=value)
            return document_id.pk
        except DocumentId.DoesNotExist:
            raise serializers.ValidationError("Invalid parent_id: DocumentId not found")
