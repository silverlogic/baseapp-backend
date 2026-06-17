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
    def description(self):
        return self.label


inheritances = []

if apps.is_installed("baseapp_profiles"):
    ProfileModel = swapper.get_model_name("baseapp_profiles", "Profile")

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(ProfileModel, on_delete=models.DO_NOTHING)

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)


class ActivityLog(*inheritances, DocumentIdMixin, RelayModel):
    id = models.UUIDField(primary_key=True, editable=False)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    user = models.ForeignKey(get_user_model(), on_delete=models.DO_NOTHING)
    ip_address = models.TextField()
    verb = models.TextField()
    visibility = models.TextField()
    url = models.TextField()
    metadata = models.JSONField()

    class Meta:
        managed = False
        db_table = "v_activity_log"
