from rest_framework import permissions, viewsets

from .views import direct_creator_upload


class CloudflareStreamUploadViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def create(self, request, *args, **kwargs):
        return direct_creator_upload(request)
