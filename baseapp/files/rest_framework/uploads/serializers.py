import swapper
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_core.models import DocumentId

from ...content_safety import allowed_content_type, file_extension

File = swapper.load_model("baseapp_files", "File")


class InitiateUploadSerializer(serializers.Serializer):
    """Serializer for initiating a multipart upload."""

    file_name = serializers.CharField(max_length=512)
    file_size = serializers.IntegerField(min_value=1)
    # Only informative: the allowlist decides the stored type, so blank (a browser that
    # doesn't know the type) or missing is fine.
    file_content_type = serializers.CharField(max_length=150, required=False, allow_blank=True)
    num_parts = serializers.IntegerField(min_value=1, max_value=10000)
    part_size = serializers.IntegerField(min_value=1)

    # Optional parent relationship via DocumentId public_id
    parent_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_file_name(self, value: str) -> str:
        """Only extensions on BASEAPP_FILES_ALLOWED_FILE_TYPES may be uploaded."""
        if allowed_content_type(value) is None:
            extension = file_extension(value)
            if extension:
                raise serializers.ValidationError(
                    _("Files of type %(extension)s are not allowed.") % {"extension": extension}
                )
            raise serializers.ValidationError(_("This file type is not allowed."))
        return value

    def validate_file_size(self, value: int) -> int:
        """Reject a declared size above MAX_FILE_UPLOAD_SIZE, naming the limit.

        Validated here, not only in UploadService, so the client gets the reason
        instead of the view's generic "Invalid upload parameters". Anonymous callers
        get BASEAPP_FILES_ANONYMOUS_MAX_FILE_SIZE when it is set.
        """
        max_file_size = getattr(settings, "MAX_FILE_UPLOAD_SIZE", 5 * 1024 * 1024 * 1024)
        request = self.context.get("request")
        anonymous_max = getattr(settings, "BASEAPP_FILES_ANONYMOUS_MAX_FILE_SIZE", None)
        if request is not None and not request.user.is_authenticated and anonymous_max:
            max_file_size = anonymous_max
        if value > max_file_size:
            raise serializers.ValidationError(
                _("File is too large. The maximum size is %(max)s.")
                % {"max": filesizeformat(max_file_size)}
            )
        return value

    def validate_parent_id(self, value):
        """Validate parent_id exists as a DocumentId public_id."""
        if not value:
            return None

        try:
            document_id = DocumentId.objects.get(public_id=value)
            return document_id.pk
        except DocumentId.DoesNotExist:
            raise serializers.ValidationError(
                [_("Invalid parent_id: DocumentId not found")]
            ) from None

    def validate(self, data):
        """Validate file size matches parts, and store the type the extension allows."""
        # The declared type is the client's word; a page type on an allowed extension would
        # be served as a page. The allowlist decides how the file is stored and served.
        data["file_content_type"] = allowed_content_type(data["file_name"])

        num_parts = data["num_parts"]
        part_size = data["part_size"]
        file_size = data["file_size"]

        min_size = (num_parts - 1) * part_size
        max_size = num_parts * part_size

        if file_size < min_size or file_size > max_size:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        _("File size %(size)s doesn't match %(parts)s parts of %(part_size)s bytes")
                        % {"size": file_size, "parts": num_parts, "part_size": part_size}
                    ]
                }
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
    # Only for anonymous uploads: proves ownership on complete, abort and attach.
    upload_token = serializers.CharField(required=False)


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
                raise serializers.ValidationError(
                    [_("Each part must have 'part_number' and 'etag'")]
                )

            if not isinstance(part["part_number"], int) or part["part_number"] < 1:
                raise serializers.ValidationError([_("part_number must be a positive integer")])

            if not isinstance(part["etag"], str) or not part["etag"]:
                raise serializers.ValidationError([_("etag must be a non-empty string")])

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
            raise serializers.ValidationError(
                [_("Invalid parent_id: DocumentId not found")]
            ) from None
