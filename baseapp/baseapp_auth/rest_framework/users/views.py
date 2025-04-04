from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.shortcuts import get_object_or_404
from rest_framework import (
    filters,
    mixins,
    permissions,
    response,
    serializers,
    status,
    viewsets,
)
from rest_framework_nested.viewsets import NestedViewSetMixin

from baseapp_core.rest_framework.decorators import action

User = get_user_model()

from django.utils.translation import gettext_lazy as _

from .parsers import SafeJSONParser
from .serializers import (
    ChangePasswordSerializer,
    UserManagePermissionSerializer,
    UserPermissionSerializer,
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

    @action(detail=False, methods=["get", "post"], serializer_class=UserPermissionSerializer)
    def permissions(self, request):
        user = request.user
        if request.method == "GET":
            permissions = user.get_all_permissions()
            return response.Response({"permissions": permissions})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return response.Response({"has_perm": user.has_perm(serializer.data["perm"])})


class PermissionsViewSet(
    NestedViewSetMixin, viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin
):
    pagination_class = None
    serializer_class = UserManagePermissionSerializer
    permission_classes = [
        permissions.IsAuthenticated,
    ]
    parent_lookup_kwargs = {"user_pk": "user__id"}

    def get_user(self):
        user_pk = self.kwargs.get("user_pk", None)
        return get_object_or_404(User, pk=user_pk) if user_pk else None

    def get_queryset(self):
        user = self.get_user()
        if user:
            if not self.request.user.has_perm("users.change_user"):
                raise serializers.ValidationError(
                    {"detail": _("You do not have permission to perform this action.")}
                )
            return user.user_permissions.all().select_related("content_type")
        return Permission.objects.all().select_related("content_type")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "user": self.get_user()}
