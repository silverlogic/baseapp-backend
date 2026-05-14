from baseapp_reports.models import (
    AbstractReport,
    AbstractReportableMetadata,
    AbstractReportType,
)


class ReportType(AbstractReportType):
    class Meta(AbstractReportType.Meta):
        pass


class Report(AbstractReport):
    class Meta(AbstractReport.Meta):
        pass


class ReportableMetadata(AbstractReportableMetadata):
    class Meta(AbstractReportableMetadata.Meta):
        pass
