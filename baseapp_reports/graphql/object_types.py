from typing import TYPE_CHECKING, Optional

import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model
from baseapp_core.plugins import shared_services

from ..models import default_reports_count
from ..permissions import VIEW_REPORT_PERMISSION
from .filters import ReportTypeFilter

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

Report = swapper.load_model("baseapp_reports", "Report")
ReportType = swapper.load_model("baseapp_reports", "ReportType")


class BaseReportTypeObjectType:
    class Meta:
        interfaces = (RelayNode,)
        model = ReportType
        fields = (
            "id",
            "key",
            "label",
            "content_types",
            "sub_types",
            "parent_type",
        )
        filterset_class = ReportTypeFilter


class ReportTypeObjectType(
    BaseReportTypeObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseReportTypeObjectType.Meta):
        pass


class ReportsInterface(graphene.Interface):
    reports_count = GenericScalar()
    reports = DjangoFilterConnectionField(get_object_type_for_model(Report))
    my_report = graphene.Field(get_object_type_for_model(Report), required=False)

    def resolve_reports_count(self, info) -> dict[str, int]:
        if service := shared_services.get("reportable_metadata"):
            return service.get_reports_count(self)
        return default_reports_count()

    def resolve_reports(self, info, **kwargs) -> "QuerySet":
        user = info.context.user
        if not user.has_perm(VIEW_REPORT_PERMISSION):
            return Report.objects.none()

        target_content_type = ContentType.objects.get_for_model(self)
        return Report.objects.filter(
            target_document__content_type=target_content_type,
            target_document__object_id=self.pk,
        ).order_by("-created")

    def resolve_my_report(self, info, **kwargs) -> "Model | None":
        if info.context.user.is_authenticated:
            target_content_type = ContentType.objects.get_for_model(self)
            return Report.objects.filter(
                target_document__content_type=target_content_type,
                target_document__object_id=self.pk,
                user=info.context.user,
            ).first()


class BaseReportObjectType:
    target = graphene.Field(RelayNode)

    class Meta:
        interfaces = (RelayNode,)
        model = Report
        fields = (
            "id",
            "user",
            "report_type",
            "report_subject",
            "created",
            "modified",
            "target",
        )
        filter_fields = {
            "id": ["exact"],
        }

    @classmethod
    def get_node(cls, info: graphene.ResolveInfo, node_id: str) -> Optional["BaseReportObjectType"]:
        node = super().get_node(info, node_id)
        if not info.context.user.has_perm(VIEW_REPORT_PERMISSION, node):
            return None
        return node

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet":
        return super().get_queryset(queryset, info)


class ReportObjectType(
    BaseReportObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseReportObjectType.Meta):
        pass
