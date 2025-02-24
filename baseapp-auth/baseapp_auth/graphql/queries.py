from baseapp_core.graphql import Node
from django.contrib.auth import get_user_model
from graphene import Field
from graphene_django.filter import DjangoFilterConnectionField

from query_optimizer import optimize

from .object_types import UserObjectType

User = get_user_model()

# @TO DO: got into a place where we need to use "DISABLE_ONLY_FIELDS_OPTIMIZATION": True
# TO AVOID "Field User.profile cannot be both deferred and traversed using select_related at the same time."
# this is happening due to executing only() for querying just requested fields in the query and then prefetch_related('profile') which is not included in the query
# not sure why graphene optimizer is doing it even though the field is not being requested (OneToOneField)
def get_user_queries(CustomObjectType):
    class UsersQueries(object):
        users = DjangoFilterConnectionField(CustomObjectType)
        user = Node.Field(CustomObjectType)

        me = Field(CustomObjectType)

        def resolve_users(self, info, **kwargs):
            if info.context.user.has_perm(f"{User._meta.app_label}.view_all_users"):
                return optimize(CustomObjectType._meta.model.objects.all(), info)
            return CustomObjectType._meta.model.objects.none()

        def resolve_me(self, info, **kwargs):
            if info.context.user.is_authenticated:
                return info.context.user
            return None

    return UsersQueries


UsersQueries = get_user_queries(UserObjectType)
