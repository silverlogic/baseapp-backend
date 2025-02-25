import swapper

from baseapp_core.graphql import Node, get_object_type_for_model
from graphene_django.filter import DjangoFilterConnectionField

ReportType = swapper.load_model("baseapp_reports", "ReportType")
Report = swapper.load_model("baseapp_reports", "Report")


class ReportTypesQueries:
    report_types = DjangoFilterConnectionField(
        get_object_type_for_model(ReportType)
    )


class ReportsQueries:
    report = Node.Field(get_object_type_for_model(Report))
