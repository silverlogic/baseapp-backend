from typing import Any

import strawberry_django
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_auth.strawberry.permissions import PermissionsInterface
from baseapp_core.strawberry import Node, django_type, type_for_model

Organization = swapper.load_model("baseapp_organizations", "Organization")

OrganizationLazyType = type_for_model(Organization)


@strawberry_django.type(Organization, name="AbstractOrganization")
class AbstractOrganizationType:
    """Organization fields, shared by the package type and project overrides."""

    pk: int | None = strawberry_django.field()

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        if not info.context.user.has_perm("baseapp_organizations.view_organization"):
            return None
        return super().get_node(info, pk)


@django_type(Organization, relations=("profile",))
class OrganizationType(AbstractOrganizationType, PermissionsInterface, Node):
    pass
