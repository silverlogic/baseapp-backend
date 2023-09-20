from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseUploadHandler(ABC):
    """Abstract interface for upload handlers (S3 vs Local)."""

    @abstractmethod
    def supports_multipart(self) -> bool:
        """Whether this handler supports true multipart uploads."""
        pass

    @abstractmethod
    def initiate_upload(self, file_obj, num_parts: int, part_size: int) -> Dict[str, Any]:
        """
        Initiate an upload and return presigned URLs.

        Returns:
            {
                'upload_id': str,
                'presigned_urls': [
                    {'part_number': 1, 'url': 'https://...'},
                    {'part_number': 2, 'url': 'https://...'},
                ],
                'expires_in': int (seconds)
            }
        """
        pass

    @abstractmethod
    def complete_upload(self, file_obj, upload_id: str, parts: List[Dict[str, Any]]) -> str:
        """
        Complete the upload.

        Args:
            parts: [{'part_number': 1, 'etag': 'xxx'}, ...]

        Returns:
            final_url: str (file URL)
        """
        pass

    @abstractmethod
    def abort_upload(self, file_obj, upload_id: str) -> None:
        """Abort and cleanup an upload."""
        pass

    @abstractmethod
    def get_file_url(self, file_obj) -> str:
        """Get the URL for accessing the file."""
        pass
