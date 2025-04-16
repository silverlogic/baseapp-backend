from django.contrib.auth.models import Group, Permission
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property


class Role(models.Model):
    name = models.CharField(unique=True, max_length=255)
    slug = models.CharField(unique=True, max_length=255)
    groups = models.ManyToManyField(Group, related_name="roles", blank=True)
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)
    exclude_permissions = models.ManyToManyField(
        Permission, related_name="excluded_permission_roles", blank=True
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "_")
        return super().save(*args, **kwargs)

    @cached_property
    def permission_list(self):
        return self.get_permission_list()

    def get_permission_list(self, user_exclude_perms=[]):
        perms = set()
        excluded_perms = user_exclude_perms + list(
            Permission.objects.filter(excluded_permission_roles__slug=self.slug).values_list(
                "codename", flat=True
            )
        )
        try:
            for group in self.groups.all():
                group_perms = group.permissions.filter(~Q(codename__in=excluded_perms)).values_list(
                    "content_type__app_label", "codename"
                )
                perm_set = {"%s.%s" % (ct, name) for ct, name in group_perms}
                perms = {*perms, *perm_set}

            group_perms = self.permissions.filter(~Q(codename__in=excluded_perms)).values_list(
                "content_type__app_label", "codename"
            )
            perm_set = {"%s.%s" % (ct, name) for ct, name in group_perms}
            perms = {*perms, *perm_set}
        except Exception:
            return perms
        return perms


class IpRestriction(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(unique=True)
    is_whitelisted = models.BooleanField(
        default=False, help_text="If checked, this IP will be whitelisted"
    )
    unrestricted_roles = models.ManyToManyField(
        Role,
        related_name="ips",
        blank=True,
        help_text="List of roles that will be unrestricted for this IP",
    )
