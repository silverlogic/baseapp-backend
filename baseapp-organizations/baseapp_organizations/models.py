import swapper
from baseapp_core.graphql.models import RelayModel
from django.apps import apps
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

inheritances = [TimeStampedModel]

if apps.is_installed("baseapp_profiles"):
    from baseapp_profiles.models import ProfilableModel

    inheritances.append(ProfilableModel)

inheritances.append(RelayModel)


class AbstractOrganization(*inheritances):
    pass

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
