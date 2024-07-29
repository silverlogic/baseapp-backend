from baseapp_core.graphql import Node

from .object_types import ReportObjectType


class ReportsQueries:
    report = Node.Field(ReportObjectType)
