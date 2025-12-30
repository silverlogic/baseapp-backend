import swapper
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

File = swapper.load_model("baseapp_files", "File")


class InitiateUploadSerializer(serializers.Serializer):
    """Serializer for initiating a multipart upload."""

    file_name = serializers.CharField(max_length=512)
    file_size = serializers.IntegerField(min_value=1)
    file_content_type = serializers.CharField(max_length=150)
    num_parts = serializers.IntegerField(min_value=1, max_value=10000)
    part_size = serializers.IntegerField(min_value=1)

    # Optional parent relationship
    parent_content_type = serializers.CharField(required=False, allow_null=True)
    parent_object_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_parent_content_type(self, value):
        """Validate and convert content type string to ID."""
        if not value:
            return None

        try:
            app_label, model = value.split(".")
            ct = ContentType.objects.get(app_label=app_label, model=model)
            return ct.id
        except (ValueError, ContentType.DoesNotExist):
            raise serializers.ValidationError("Invalid content type")

    def validate(self, data):
        """Cross-field validation."""
        # Both parent fields must be provided together
        has_ct = data.get("parent_content_type") is not None
        has_id = data.get("parent_object_id") is not None

        if has_ct != has_id:
            raise serializers.ValidationError(
                "Both parent_content_type and parent_object_id must be provided together"
            )

        # Rename parent_content_type to parent_content_type_id for service layer
        if "parent_content_type" in data:
            data["parent_content_type_id"] = data.pop("parent_content_type")

        # Validate file size matches parts
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

    id = serializers.IntegerField(source="file_obj.id")
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

    parent_content_type = serializers.CharField()
    parent_object_id = serializers.IntegerField()

    def validate_parent_content_type(self, value):
        """Validate and convert content type string to ID."""
        try:
            app_label, model = value.split(".")
            ct = ContentType.objects.get(app_label=app_label, model=model)
            return ct.id
        except (ValueError, ContentType.DoesNotExist):
            raise serializers.ValidationError("Invalid content type")

    def validate(self, data):
        """Rename parent_content_type to parent_content_type_id for model."""
        if "parent_content_type" in data:
            data["parent_content_type_id"] = data.pop("parent_content_type")
        return data
