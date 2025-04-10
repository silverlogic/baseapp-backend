import swapper
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import RelayModel


class VisibilityTypes(models.IntegerChoices):
    PUBLIC = 0, _("public")
    PRIVATE = 1, _("private")
    INTERNAL = 2, _("internal")

    @property
    def description(self):
        return self.label


class ActivityLog(RelayModel):
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    user = models.ForeignKey(get_user_model(), on_delete=models.DO_NOTHING)
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"), on_delete=models.DO_NOTHING
    )
    ip_address = models.TextField()
    verb = models.TextField()
    visibility = models.TextField()
    url = models.TextField()
    metadata = models.JSONField()

    class Meta:
        managed = False
        db_table = "v_activity_log"
