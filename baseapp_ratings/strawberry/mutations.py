import strawberry
from django.apps import apps
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .interfaces import RatingsInterface
from .types import RateLazyType


@strawberry.input(name="RateCreateInput")
class RateCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    value: int
    if apps.is_installed("baseapp_profiles"):
        profile_id: strawberry.ID | None = UNSET


@strawberry.type(name="RateCreatePayload")
class RateCreatePayload(RelayMutationPayload):
    rate: Edge[RateLazyType] | None = None
    target: RatingsInterface | None = None


@strawberry.type
class RatingsMutations:
    rate_create = graphene_relay_mutation(
        graphene_mutations.RateCreate, RateCreateInput, RateCreatePayload
    )
