from rest_framework import permissions, response, viewsets
from rest_framework.decorators import list_route

from .serializers import ChangePasswordSerializer, UserSerializer


class UsersViewSet(viewsets.GenericViewSet):
    serializer_class = UserSerializer

    @list_route(methods=['GET'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        user = request.user
        serializer = self.get_serializer(user)
        return response.Response(serializer.data)

    @list_route(methods=['POST'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({'detail': 'success'})
