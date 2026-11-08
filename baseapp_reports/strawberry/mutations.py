import strawberry
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .interfaces import ReportsInterface
from .types import ReportLazyType


@strawberry.input(name="ReportCreateInput")
class ReportCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    report_type_id: strawberry.ID
    report_subject: str | None = UNSET


@strawberry.type(name="ReportCreatePayload")
class ReportCreatePayload(RelayMutationPayload):
    report: Edge[ReportLazyType] | None = None
    target: ReportsInterface | None = None


@strawberry.type
class ReportsMutations:
    report_create = graphene_relay_mutation(
        graphene_mutations.ReportCreate, ReportCreateInput, ReportCreatePayload
    )
