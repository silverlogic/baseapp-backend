import strawberry
from django.apps import apps
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .interfaces import ReactionsInterface
from .types import ReactionLazyType, ReactionTypesEnum


@strawberry.input(name="ReactionToggleInput")
class ReactionToggleInput(RelayMutationInput):
    target_object_id: strawberry.ID
    reaction_type: ReactionTypesEnum
    if apps.is_installed("baseapp_profiles"):
        profile_object_id: strawberry.ID | None = UNSET


@strawberry.type(name="ReactionTogglePayload")
class ReactionTogglePayload(RelayMutationPayload):
    reaction: Edge[ReactionLazyType] | None = None
    target: ReactionsInterface | None = None
    reaction_deleted_id: strawberry.ID | None = None


@strawberry.type
class ReactionsMutations:
    reaction_toggle = graphene_relay_mutation(
        graphene_mutations.ReactionToggle, ReactionToggleInput, ReactionTogglePayload
    )
