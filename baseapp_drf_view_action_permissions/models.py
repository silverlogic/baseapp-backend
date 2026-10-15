import logging

from django.contrib.auth.models import Group, Permission
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class Role(models.Model):
    name = models.CharField(_("name"), unique=True, max_length=255)
    slug = models.CharField(_("slug"), unique=True, max_length=255)
    groups = models.ManyToManyField(
        Group, verbose_name=_("groups"), related_name="roles", blank=True
    )
    permissions = models.ManyToManyField(
        Permission, verbose_name=_("permissions"), related_name="roles", blank=True
    )
    exclude_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("exclude permissions"),
        related_name="excluded_permission_roles",
        blank=True,
    )

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "_")
        return super().save(*args, **kwargs)

    @cached_property
    def permission_list(self) -> set[str]:
        return self.get_permission_list()

    def get_permission_list(self, user_exclude_perms: list | None = None) -> set:
        if user_exclude_perms is None:
            user_exclude_perms = []
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
                perms |= {"%s.%s" % (ct, name) for ct, name in group_perms}

            group_perms = self.permissions.filter(~Q(codename__in=excluded_perms)).values_list(
                "content_type__app_label", "codename"
            )
            perms |= {"%s.%s" % (ct, name) for ct, name in group_perms}
        except Exception:
            logger.exception(
                "Failed to resolve permission list for role %r (id=%s)",
                getattr(self, "name", None),
                getattr(self, "pk", None),
            )
        return perms


class IpRestriction(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    modified_at = models.DateTimeField(_("modified at"), auto_now=True)
    ip_address = models.GenericIPAddressField(_("IP address"), unique=True)
    is_whitelisted = models.BooleanField(
        _("is whitelisted"), default=False, help_text=_("If checked, this IP will be whitelisted")
    )
    unrestricted_roles = models.ManyToManyField(
        Role,
        verbose_name=_("unrestricted roles"),
        related_name="ips",
        blank=True,
        help_text=_("List of roles that will be unrestricted for this IP"),
    )

    class Meta:
        verbose_name = _("IP restriction")
        verbose_name_plural = _("IP restrictions")
