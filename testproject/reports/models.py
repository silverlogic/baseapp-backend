from baseapp_reports.models import (
    AbstractReport,
    AbstractReportableMetadata,
    AbstractReportType,
)


class ReportType(AbstractReportType):
    class Meta(AbstractReportType.Meta):
        db_table = "baseapp_reports_reporttype"

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_reports.graphql.object_types import ReportTypeObjectType

        return ReportTypeObjectType


class Report(AbstractReport):
    class Meta(AbstractReport.Meta):
        db_table = "baseapp_reports_report"

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_reports.graphql.object_types import ReportObjectType

        return ReportObjectType


class ReportableMetadata(AbstractReportableMetadata):
    class Meta(AbstractReportableMetadata.Meta):
        pass
