import strawberry
from django.apps import apps
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .interfaces import CommentsInterface
from .types import CommentLazyType


@strawberry.input(name="CommentCreateInput")
class CommentCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    in_reply_to_id: strawberry.ID | None = UNSET
    body: str
    mentioned_profile_ids: list[strawberry.ID | None] | None = UNSET
    if apps.is_installed("baseapp_profiles"):
        profile_id: strawberry.ID | None = UNSET


@strawberry.type(name="CommentCreatePayload")
class CommentCreatePayload(RelayMutationPayload):
    comment: Edge[CommentLazyType] | None = None


@strawberry.input(name="CommentUpdateInput")
class CommentUpdateInput(RelayMutationInput):
    id: strawberry.ID
    body: str
    mentioned_profile_ids: list[strawberry.ID | None] | None = UNSET


@strawberry.type(name="CommentUpdatePayload")
class CommentUpdatePayload(RelayMutationPayload):
    comment: CommentLazyType | None = None


@strawberry.input(name="CommentPinInput")
class CommentPinInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="CommentPinPayload")
class CommentPinPayload(RelayMutationPayload):
    comment: CommentLazyType | None = None


@strawberry.input(name="CommentDeleteInput")
class CommentDeleteInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="CommentDeletePayload")
class CommentDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None
    target: CommentsInterface | None = None
    in_reply_to: CommentLazyType | None = None


g = graphene_mutations


@strawberry.type
class CommentsMutations:
    comment_create = graphene_relay_mutation(
        g.CommentCreate, CommentCreateInput, CommentCreatePayload
    )
    comment_update = graphene_relay_mutation(
        g.CommentUpdate, CommentUpdateInput, CommentUpdatePayload
    )
    comment_pin = graphene_relay_mutation(g.CommentPin, CommentPinInput, CommentPinPayload)
    comment_delete = graphene_relay_mutation(
        g.CommentDelete, CommentDeleteInput, CommentDeletePayload
    )
