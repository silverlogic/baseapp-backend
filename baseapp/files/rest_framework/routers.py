from baseapp_core.rest_framework.routers import DefaultRouter

from .files.views import FilesViewSet
from .uploads.presigned_views import PresignedUploadViewSet
from .uploads.views import FileUploadViewSet

files_router = DefaultRouter(trailing_slash=False)

files_router.register(
    r"files/presigned-uploads", PresignedUploadViewSet, basename="presigned-uploads"
)
files_router.register(r"files/uploads", FileUploadViewSet, basename="file-uploads")
files_router.register(r"files", FilesViewSet, basename="files")
