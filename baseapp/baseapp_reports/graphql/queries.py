import swapper
import graphene

from django.contrib.contenttypes.models import ContentType
from baseapp_core.graphql import Node, get_object_type_for_model, get_obj_from_relay_id
from graphene_django.filter import DjangoFilterConnectionField

ReportType = swapper.load_model("baseapp_reports", "ReportType")
Report = swapper.load_model("baseapp_reports", "Report")
ReportTypeObjectType = ReportType.get_graphql_object_type()
ReportObjectType = Report.get_graphql_object_type()


class ReportTypesQueries:
    report_types = graphene.Field(
        ReportTypeObjectType,
        target_object_id=graphene.ID(required=False)
    )
    # report_types = Node.Field(ReportTypeObjectType)
    # report_types = DjangoFilterConnectionField(ReportObjectType)
    all_report_types = DjangoFilterConnectionField(ReportTypeObjectType)

    def resolve_report_types(self, info, **kwargs):
        print("========================XABLAU=========================")
        target_object_id = kwargs.get("target_object_id")
        if not target_object_id:
            return ReportType.objects.all()
        obj = get_obj_from_relay_id(info, target_object_id)
        print(obj)
        content_type = ContentType.objects.get_for_model(obj)
        return ReportType.objects.filter(content_types__pk=content_type.pk)


class ReportsQueries:
    report = Node.Field(get_object_type_for_model(Report))
