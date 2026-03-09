from baseapp_reports.models import AbstractBaseReport, AbstractBaseReportType


class ReportType(AbstractBaseReportType):
    class Meta(AbstractBaseReportType.Meta):
        db_table = "baseapp_reports_reporttype"

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_reports.graphql.object_types import ReportTypeObjectType

        return ReportTypeObjectType


class Report(AbstractBaseReport):
    class Meta(AbstractBaseReport.Meta):
        db_table = "baseapp_reports_report"

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_reports.graphql.object_types import ReportObjectType

        return ReportObjectType
