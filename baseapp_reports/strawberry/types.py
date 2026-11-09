from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import Node, django_type, type_for_model

from ..permissions import VIEW_REPORT_PERMISSION
from .filters import ReportTypeFilter

Report = swapper.load_model("baseapp_reports", "Report")
ReportType = swapper.load_model("baseapp_reports", "ReportType")

ReportLazyType = type_for_model(Report)
ReportTypeLazyType = type_for_model(ReportType)


@strawberry_django.type(ReportType, name="AbstractReportType")
class AbstractReportTypeType:
    """ReportType fields, shared by the package type and project overrides."""

    key: strawberry.auto
    label: strawberry.auto


@django_type(
    ReportType,
    filterset_class=ReportTypeFilter,
    relations=("content_types", "sub_types", "parent_type"),
)
class ReportTypeType(AbstractReportTypeType, Node):
    pass


@strawberry_django.type(Report, name="AbstractReport")
class AbstractReportType:
    """Report fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    report_subject: strawberry.auto

    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["target_document_id"],
        prefetch_related=["target_document__content_object"],
    )
    def target(self, info: Info) -> Any:
        target = self.target
        if target is not None and not hasattr(target, "mapped_public_id"):
            # The prefetched DocumentId already holds the relay id: no lookup per row.
            target.mapped_public_id = self.target_document.public_id
        return target

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if not info.context.user.has_perm(VIEW_REPORT_PERMISSION, node):
            return None
        return node


@django_type(Report, relations=("user", "report_type"))
class ReportObjectType(AbstractReportType, Node):
    pass
