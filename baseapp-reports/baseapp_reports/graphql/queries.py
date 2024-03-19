from baseapp_core.graphql import Node

from .object_types import ReportNode


class ReportsQuery:
    # TO DO: fix permission, follow target until its not a Comment anymore and check if request.user has permission to see
    report = Node.Field(ReportNode)
