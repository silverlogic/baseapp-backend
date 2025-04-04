import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import DjangoObjectType, get_object_type_for_model

Report = swapper.load_model("baseapp_reports", "Report")

ReportTypesEnum = graphene.Enum.from_enum(Report.ReportTypes)


def create_object_type_from_enum(name, enum):
    fields = {}
    for reaction_type in enum:
        fields[reaction_type.name] = graphene.Int()
    fields["total"] = graphene.Int()
    return type(name, (graphene.ObjectType,), fields)


ReportsCount = create_object_type_from_enum("ReportsCount", Report.ReportTypes)


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
    report_type = graphene.Field(ReportTypesEnum)

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
