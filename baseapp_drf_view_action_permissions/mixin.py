from django.contrib.auth.models import Permission, PermissionsMixin
from django.db import models
from django.utils.functional import cached_property

from .models import Role


class PermissionModelMixin(PermissionsMixin):
    """
    A mixin class that adds the fields and methods necessary to support
    Django's Action Permission.
    """

    role = models.ForeignKey(
        Role, related_name="users", blank=True, null=True, on_delete=models.SET_NULL
    )
    exclude_permissions = models.ManyToManyField(
        Permission, related_name="excluded_permission_users", blank=True
    )

    class Meta:
        abstract = True

    def has_perm(self, perm, obj=None):
        return super().has_perm(perm, obj) or perm in self.permission_list

    def has_perms(self, perms, obj=None):
        return all(self.has_perm(perm, obj) for perm in perms)

    @cached_property
    def permission_list(self):
        perms = super().get_all_permissions()
        excluded_perms = list(
            Permission.objects.filter(excluded_permission_users__email=self.email).values_list(
                "codename", flat=True
            )
        )

        if self.role:
            role_perms = self.role.get_permission_list(excluded_perms)
            perms = {*perms, *role_perms}

        return perms
