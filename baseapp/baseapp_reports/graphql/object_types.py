from django.contrib.contenttypes.models import ContentType

import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType, get_object_type_for_model
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from .filters import ReportTypeFilter

Report = swapper.load_model("baseapp_reports", "Report")
ReportType = swapper.load_model("baseapp_reports", "ReportType")


def create_object_type_from_enum(name):
    fields = {}
    # for reaction_type in ReportType.objects.all():
    #     fields[reaction_type.name] = graphene.Int()
    fields["total"] = graphene.Int()
    return type(name, (graphene.ObjectType,), fields)


ReportsCount = create_object_type_from_enum("ReportsCount")


class BaseReportTypeObjectType:
    class Meta:
        interfaces = (relay.Node,)
        model = ReportType
        fields = (
            "id",
            "name",
            "label",
            "content_types",
            "sub_types",
            "parent_type",
        )
        filterset_class = ReportTypeFilter
        filter_fields = {
            "id": ["exact"],
        }


class ReportTypeObjectType(
    BaseReportTypeObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseReportTypeObjectType.Meta):
        pass


# class ReportTypesInterface(relay.Node):
#     report_types = DjangoFilterConnectionField(ReportTypeObjectType)
#     all_report_types = DjangoFilterConnectionField(ReportTypeObjectType)

#     def resolve_all_report_types(self, info, **kwargs):
#         print("========================XABLAU=========================")
#         target_object_id = kwargs.get("target_object_id")
#         if not target_object_id:
#             return ReportType.objects.all()
#         obj = get_obj_from_relay_id(info, target_object_id)
#         print(obj)
#         content_type = ContentType.objects.get_for_model(obj)
#         return ReportType.objects.filter(content_types__pk=content_type.pk)


class ReportsInterface(relay.Node):
    reports_count = graphene.Field(ReportsCount)
    reports = DjangoFilterConnectionField(get_object_type_for_model(Report))
    my_reports = graphene.Field(get_object_type_for_model(Report), required=False)

    def resolve_reactions(self, info, **kwargs):
        target_content_type = ContentType.objects.get_for_model(self)
        return Report.objects.filter(
            target_content_type=target_content_type,
            target_object_id=self.pk,
        ).order_by("-created")

    def resolve_my_reaction(self, info, **kwargs):
        if info.context.user.is_authenticated:
            target_content_type = ContentType.objects.get_for_model(self)
            return Report.objects.filter(
                target_content_type=target_content_type,
                target_object_id=self.pk,
                user=info.context.user,
            ).first()


class BaseReportObjectType:
    target = graphene.Field(relay.Node)

    class Meta:
        interfaces = (relay.Node,)
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
    def get_node(self, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm("baseapp_reports.view_report", node):
            return None
        return node


class ReportObjectType(
    BaseReportObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseReportObjectType.Meta):
        pass
