from collections.abc import Iterable
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import CountedConnection, model_from_info, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.scalars import GenericScalar

from ..models import default_reports_count
from ..permissions import VIEW_REPORT_PERMISSION
from .filters import ReportFilter

Report = swapper.load_model("baseapp_reports", "Report")
ReportLazyType = type_for_model(Report)


def _reports_count_annotation(info: Info) -> Any:
    service = shared_services.get("reportable_metadata")
    return service.get_annotations(model_from_info(info))["_reportable_reports_count"]


@strawberry.interface(name="ReportsInterface")
class ReportsInterface:
    """Reports fields for any reportable model. Optimizer hints live on the fields themselves."""

    @strawberry_django.field(annotate={"_reportable_reports_count": _reports_count_annotation})
    def reports_count(self, info: Info) -> GenericScalar | None:
        if service := shared_services.get("reportable_metadata"):
            return service.get_reports_count(self)
        return default_reports_count()

    @connection(
        CountedConnection[ReportLazyType] | None,
        filterset_class=ReportFilter,
        filter_overrides={"id": strawberry.ID},
    )
    def reports(self, info: Info) -> Iterable[Model]:
        if not info.context.user.has_perm(VIEW_REPORT_PERMISSION):
            return Report.objects.none()
        return Report.objects.filter(
            target_document__content_type=ContentType.objects.get_for_model(self),
            target_document__object_id=self.pk,
        ).order_by("-created")

    @strawberry.field(graphql_type=Optional[ReportLazyType])
    def my_report(self, info: Info) -> Any:
        if not info.context.user.is_authenticated:
            return None
        return Report.objects.filter(
            target_document__content_type=ContentType.objects.get_for_model(self),
            target_document__object_id=self.pk,
            user=info.context.user,
        ).first()
