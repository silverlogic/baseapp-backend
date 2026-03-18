import swapper
from django.apps import apps
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin

inheritances = []

if apps.is_installed("baseapp_profiles"):

    class ProfilableModel(models.Model):
        profile = models.OneToOneField(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            related_name="%(class)s",
            on_delete=models.PROTECT,
            verbose_name=_("profile"),
            null=True,
            blank=True,
        )

        class Meta:
            abstract = True

    inheritances.append(ProfilableModel)


class AbstractOrganization(*inheritances, DocumentIdMixin, RelayModel, TimeStampedModel):
    name = models.CharField(
        _("name"),
        max_length=255,
        blank=True,
        null=True,
    )

    class Meta:
        abstract = True
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import OrganizationObjectType

        return OrganizationObjectType


class Organization(AbstractOrganization):
    class Meta(AbstractOrganization.Meta):
        swappable = swapper.swappable_setting("baseapp_organizations", "Organization")
