from baseapp_auth.graphql.object_types import UserObjectType as BaseUserObjectType

from baseapp_reports.graphql.object_types import ReportsInterface


class UserNode(BaseUserObjectType):
    class Meta(BaseUserObjectType.Meta):
        interfaces = BaseUserObjectType.Meta.interfaces + (ReportsInterface,)
