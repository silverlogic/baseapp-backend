from baseapp_core.rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import (
    filters,
    mixins,
    permissions,
    response,
    serializers,
    status,
    viewsets,
)

User = get_user_model()

from .parsers import SafeJSONParser
from .serializers import (
    ChangePasswordSerializer,
    ConfirmEmailSerializer,
    UserSerializer,
)


class UpdateSelfPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in ("PUT", "PATCH"):
            if not request.user.is_authenticated or request.user != obj:
                return False
        return True


class UsersViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UserSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        UpdateSelfPermission,
    ]
    filter_backends = (filters.SearchFilter,)
    search_fields = ("first_name", "last_name")

    def get_queryset(self):
        return User.objects.all().order_by("id")

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def me(self, request):
        user = request.user
        serializer = self.get_serializer(user)
        return response.Response(serializer.data)

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[permissions.IsAuthenticated],
        serializer_class=ChangePasswordSerializer,
        parser_classes=[SafeJSONParser],
    )
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "success"})

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[],
        serializer_class=ConfirmEmailSerializer,
    )
    def confirm_email(self, request, pk=None, *args, **kwargs):
        try:
            user = self.get_object()
        except Http404:
            raise serializers.ValidationError(_("Invalid token"))
        serializer = self.get_serializer(data=request.data, instance=user)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({})

    @action(
        detail=False,
        methods=["DELETE"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def delete_account(self, request):
        user = request.user
        if user.is_superuser:
            user.is_active = False
            user.save()
        else:
            user.delete()
        return response.Response(data={}, status=status.HTTP_204_NO_CONTENT)
