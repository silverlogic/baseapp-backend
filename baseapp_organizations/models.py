from typing import TYPE_CHECKING

import swapper
from django.apps import apps
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin

if TYPE_CHECKING:
    from baseapp_core.graphql import DjangoObjectType

inheritances = []

if apps.is_installed("baseapp_profiles"):
    from baseapp_profiles.models import ProfilableModel

    inheritances.append(ProfilableModel)


class AbstractOrganization(*inheritances, DocumentIdMixin, RelayModel, TimeStampedModel):
    profile_name_sql = "NEW.name"

    name = models.CharField(
        _("name"),
        max_length=255,
        blank=True,
        null=True,
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_organizations", "Organization")
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")

    def __str__(self) -> str:
        return self.name or ""

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import OrganizationObjectType

        return OrganizationObjectType
