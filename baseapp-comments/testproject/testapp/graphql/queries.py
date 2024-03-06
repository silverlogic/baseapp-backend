import graphene

from .object_types import UserObjectType


class UsersQuery:
    me = graphene.Field(UserObjectType)

    def resolve_me(self, info):
        if info.context.user.is_authenticated:
            return info.context.user
