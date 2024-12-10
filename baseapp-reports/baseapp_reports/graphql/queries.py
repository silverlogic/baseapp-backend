import swapper
from baseapp_core.graphql import Node, get_object_type_for_model


from .object_types import ReportObjectType

Report = swapper.load_model("baseapp_reports", "Report")


class ReportsQueries:
    report = Node.Field(get_object_type_for_model(Report))
