import swapper
from baseapp_core.graphql import RelayModel
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from pghistory.models import Context


class VisibilityTypes(models.IntegerChoices):
    PUBLIC = 0, _("public")
    PRIVATE = 1, _("private")
    INTERNAL = 2, _("internal")

    @property
    def description(self):
        return self.label


class ActivityLogQuerySet(models.QuerySet):
    def annotated_metadata(self) -> "ActivityLogQuerySet":
        """
        Annotate queryset with metadata fields.
        Returns an annotated queryset with user_id, profile_id, url, verb,
        visibility, and ip_address from the metadata JSON field.
        """
        return self.annotate(
            user_id=models.F("metadata__user"),
            profile_id=models.F("metadata__profile"),
            url=models.F("metadata__url"),
            verb=models.F("metadata__verb"),
            visibility=models.F("metadata__visibility"),
            ip_address=models.F("metadata__ip_address"),
        )


class ActivityLogQuerySetManager(models.Manager):
    def get_queryset(self):
        return ActivityLogQuerySet(self.model, using=self._db).annotated_metadata()


class ActivityLogContextManagers(models.Model):
    objects = ActivityLogQuerySetManager()

    class Meta:
        abstract = True


class ActivityLog(RelayModel, ActivityLogContextManagers, Context):
    class Meta:
        proxy = True

    @cached_property
    def user(self):
        """Return the associated user or None if not found."""
        if self.user_id:
            User = get_user_model()
            try:
                return User.objects.get(pk=self.user_id)
            except User.DoesNotExist:
                return None

    @cached_property
    def profile(self):
        """Return the associated profile or None if not found."""
        if self.profile_id:
            Profile = swapper.load_model("baseapp_profiles", "Profile")
            try:
                return Profile.objects.get(pk=self.profile_id)
            except Profile.DoesNotExist:
                return None
