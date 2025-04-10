from baseapp_auth.graphql.object_types import UserObjectType as BaseUserObjectType


class UserNode(BaseUserObjectType):
    class Meta(BaseUserObjectType.Meta):
        interfaces = BaseUserObjectType.Meta.interfaces
