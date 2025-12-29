import swapper
from rest_framework_tus.handlers import BaseHandler


class FileUploadSaveHandler(BaseHandler):
    """
    Custom TUS upload handler that updates file metadata when upload is complete.

    Since we write directly to the file field during upload, this handler only
    needs to update the metadata fields when the upload completes.
    """

    def handle(self, upload):
        """
        Update file metadata when upload is complete.

        Args:
            upload: The File instance (swappable model)
        """
        FileModel = swapper.load_model("baseapp_files", "File")

        if not isinstance(upload, FileModel):
            return

        # Only process if upload is complete
        if not upload.is_complete():
            return

        # Update file metadata from upload_metadata
        filename = upload.upload_metadata.get("filename") or upload.filename
        if filename:
            upload.file_name = filename

        upload.file_size = upload.upload_length

        content_type = upload.upload_metadata.get("content_type")
        if content_type:
            upload.file_content_type = content_type

        # Save the updated metadata
        upload.save()
