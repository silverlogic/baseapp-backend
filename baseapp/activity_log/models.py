import swapper
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentIdMixin


class VisibilityTypes(models.IntegerChoices):
    PUBLIC = 0, _("public")
    PRIVATE = 1, _("private")
    INTERNAL = 2, _("internal")

    @property
    def description(self) -> str:
        return self.label


inheritances = []

if apps.is_installed("baseapp_profiles"):
    ProfileModel = swapper.get_model_name("baseapp_profiles", "Profile")

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(
            ProfileModel, verbose_name=_("profile"), on_delete=models.DO_NOTHING
        )

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)


class ActivityLog(*inheritances, DocumentIdMixin, RelayModel):
    id = models.UUIDField(_("id"), primary_key=True, editable=False)
    created_at = models.DateTimeField(_("created at"))
    updated_at = models.DateTimeField(_("updated at"))
    user = models.ForeignKey(get_user_model(), verbose_name=_("user"), on_delete=models.DO_NOTHING)
    ip_address = models.TextField(_("IP address"))
    verb = models.TextField(_("verb"))
    visibility = models.TextField(_("visibility"))
    url = models.TextField(_("URL"))
    metadata = models.JSONField(_("metadata"))

    class Meta:
        managed = False
        db_table = "v_activity_log"
        verbose_name = _("activity log")
        verbose_name_plural = _("activity logs")
