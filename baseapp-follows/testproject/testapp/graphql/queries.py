import graphene

from .object_types import UserNode


class UsersQuery:
    me = graphene.Field(UserNode)

    def resolve_me(self, info):
        if info.context.user.is_authenticated:
            return info.context.user
