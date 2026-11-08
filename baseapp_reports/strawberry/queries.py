from collections.abc import Iterable

import strawberry
import swapper
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection
from baseapp_core.strawberry.connections import apply_filterset, connection
from baseapp_core.strawberry.relay import get_instance_from_global_id, typed_node_field

from ..graphql.filters import ReportTypeFilter
from .types import ReportLazyType, ReportTypeLazyType

ReportType = swapper.load_model("baseapp_reports", "ReportType")


@strawberry.type
class ReportsQueries:
    report = typed_node_field(ReportLazyType)
    report_types = typed_node_field(ReportTypeLazyType)

    @connection(CountedConnection[ReportTypeLazyType] | None)
    def all_report_types(
        self,
        info: Info,
        top_level_only: bool | None = None,
        target_object_id: str | None = None,
    ) -> Iterable[Model]:
        queryset = ReportType.objects.all()
        if target_object_id:
            target = get_instance_from_global_id(info, target_object_id)
            content_type = ContentType.objects.get_for_model(target)
            queryset = queryset.filter(content_types__pk=content_type.pk)
        filters = {"top_level_only": top_level_only, "target_object_id": target_object_id}
        return apply_filterset(ReportTypeFilter, queryset, filters, info)
