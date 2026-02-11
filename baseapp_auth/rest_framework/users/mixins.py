from django.contrib.auth.models import Permission
from django.utils.translation import gettext_lazy as _
from rest_framework import response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from baseapp_auth.utils.normalize_permission import normalize_permission


class PermissionsActionMixin:
    """
    Instance-based permissions endpoint.

    Supports:
    - GET /<resource>/<pk>/permissions
    - GET /<resource>/<pk>/permissions?perm=a.b
    - GET /<resource>/<pk>/permissions?perm=a.b&perm=c.d
    """

    permission_query_param = "perm"

    def get_model_permissions_queryset(self, instance):
        opts = instance._meta
        return Permission.objects.filter(
            content_type__app_label=opts.app_label,
            content_type__model=opts.model_name,
        )

    @action(detail=True, methods=["get"])
    def permissions(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        raw_perms = request.query_params.getlist(self.permission_query_param)

        try:
            perms = [normalize_permission(p, instance) for p in raw_perms]
        except (AttributeError, TypeError) as err:
            raise ValidationError({"perm": _("Invalid permission format.")}) from err

        for perm in perms:
            if "." not in perm:
                raise ValidationError(
                    {"perm": _("Invalid permission format. Expected app_label.codename.")}
                )

        if perms:
            results = {perm: user.has_perm(perm, instance) for perm in perms}

            return response.Response({"permissions": results})

        perms_qs = self.get_model_permissions_queryset(instance)

        perm_keys = {normalize_permission(p.codename, instance) for p in perms_qs}

        permissions_map = {perm: user.has_perm(perm, instance) for perm in perm_keys}

        return response.Response({"permissions": permissions_map})
