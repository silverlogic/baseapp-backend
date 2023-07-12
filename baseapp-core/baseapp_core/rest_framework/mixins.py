from rest_framework import status
from rest_framework.response import Response


class DestroyModelMixin:
    """Destroy mixin that returns empty object as response.

    iOS requires that every response contains a JSON serializable
    object because of the framework they use.

    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({}, status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.delete()
