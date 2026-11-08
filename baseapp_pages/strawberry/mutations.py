import strawberry
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import (
    delete_node_mutation,
    graphene_relay_mutation,
)

from ..graphql import mutations as graphene_mutations
from .types import PageLazyType


@strawberry.input(name="PageCreateInput")
class PageCreateInput(RelayMutationInput):
    user: str | None = UNSET
    title: str | None = UNSET
    body: str | None = UNSET
    url_path: str | None = UNSET


@strawberry.type(name="PageCreatePayload")
class PageCreatePayload(RelayMutationPayload):
    page: Edge[PageLazyType] | None = None


@strawberry.input(name="PageEditInput")
class PageEditInput(RelayMutationInput):
    id: strawberry.ID
    user: str | None = UNSET
    title: str | None = UNSET
    body: str | None = UNSET
    url_path: str | None = UNSET


@strawberry.type(name="PageEditPayload")
class PageEditPayload(RelayMutationPayload):
    page: PageLazyType | None = None


@strawberry.type
class PagesMutations:
    page_create = graphene_relay_mutation(
        graphene_mutations.PageCreate, PageCreateInput, PageCreatePayload
    )
    page_edit = graphene_relay_mutation(graphene_mutations.PageEdit, PageEditInput, PageEditPayload)
    page_delete = delete_node_mutation()
