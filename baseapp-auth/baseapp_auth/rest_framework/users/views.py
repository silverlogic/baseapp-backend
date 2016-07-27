from rest_framework import filters, mixins, permissions, response, viewsets
from rest_framework.decorators import list_route

from apps.users.models import User

from .serializers import ChangePasswordSerializer, UserSerializer


class UpdateSelfPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in ('PUT', 'PATCH'):
            if not request.user.is_authenticated() or request.user != obj:
                return False
        return True


class UsersViewSet(mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin,
                   mixins.ListModelMixin,
                   viewsets.GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = (UpdateSelfPermission,)
    queryset = User.objects.all()
    filter_backends = (filters.SearchFilter,)
    search_fields = ('first_name', 'last_name',)

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
