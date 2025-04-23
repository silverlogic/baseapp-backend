import swapper
from django.contrib.contenttypes.models import ContentType
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node, get_obj_from_relay_id, get_object_type_for_model

ReportType = swapper.load_model("baseapp_reports", "ReportType")
Report = swapper.load_model("baseapp_reports", "Report")
ReportTypeObjectType = ReportType.get_graphql_object_type()
ReportObjectType = Report.get_graphql_object_type()


class ReportsQueries:
    report = Node.Field(get_object_type_for_model(Report))
    report_types = Node.Field(ReportTypeObjectType)
    all_report_types = DjangoFilterConnectionField(ReportTypeObjectType)

    def resolve_all_report_types(self, info, **kwargs):
        target_object_id = kwargs.get("target_object_id")
        if not target_object_id:
            return ReportType.objects.all()
        obj = get_obj_from_relay_id(info, target_object_id)
        content_type = ContentType.objects.get_for_model(obj)
        return ReportType.objects.filter(content_types__pk=content_type.pk)
