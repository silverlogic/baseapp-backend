import strawberry

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .interfaces import FollowsInterface
from .types import FollowLazyType


@strawberry.input(name="FollowToggleInput")
class FollowToggleInput(RelayMutationInput):
    actor_object_id: strawberry.ID
    target_object_id: strawberry.ID


@strawberry.type(name="FollowTogglePayload")
class FollowTogglePayload(RelayMutationPayload):
    follow: Edge[FollowLazyType] | None = None
    target: FollowsInterface | None = None
    actor: FollowsInterface | None = None
    follow_deleted_id: strawberry.ID | None = None


@strawberry.type
class FollowsMutations:
    follow_toggle = graphene_relay_mutation(
        graphene_mutations.FollowToggle, FollowToggleInput, FollowTogglePayload
    )
