import swapper
from django.apps import apps
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel

inheritances = [TimeStampedModel]

if apps.is_installed("baseapp_profiles"):
    from baseapp_profiles.models import ProfilableModel

    inheritances.append(ProfilableModel)

inheritances.append(RelayModel)


class AbstractOrganization(*inheritances):
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
