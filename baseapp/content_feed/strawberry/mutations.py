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

from ..graphql import mutations as g

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")


@strawberry.input(name="ContentPostCreateInput")
class ContentPostCreateInput(RelayMutationInput):
    content: str
    is_reactions_enabled: bool
    mentioned_profile_ids: list[strawberry.ID | None] | None = UNSET


@strawberry.type(name="ContentPostCreatePayload")
class ContentPostCreatePayload(RelayMutationPayload):
    content_post: Edge[type_for_model(ContentPost)] | None = None


@strawberry.type
class ContentFeedMutations:
    content_post_create = graphene_relay_mutation(
        g.ContentPostCreate, ContentPostCreateInput, ContentPostCreatePayload
    )
