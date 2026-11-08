import strawberry
import swapper
from strawberry import UNSET

from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .types import OrganizationLazyType

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileLazyType = type_for_model(Profile)


@strawberry.input(name="OrganizationCreateInput")
class OrganizationCreateInput(RelayMutationInput):
    name: str
    url_path: str | None = UNSET


@strawberry.type(name="OrganizationCreatePayload")
class OrganizationCreatePayload(RelayMutationPayload):
    organization: Edge[OrganizationLazyType] | None = None
    profile: Edge[ProfileLazyType] | None = None


@strawberry.type
class OrganizationsMutations:
    organization_create = graphene_relay_mutation(
        graphene_mutations.OrganizationCreate, OrganizationCreateInput, OrganizationCreatePayload
    )
