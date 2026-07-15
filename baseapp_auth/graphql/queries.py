from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from graphene import Field
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node

from .object_types import UserObjectType

if TYPE_CHECKING:
    from django.db.models import QuerySet

User = get_user_model()


def get_user_queries(CustomObjectType) -> type:
    class UsersQueries(object):
        users = DjangoFilterConnectionField(CustomObjectType)
        user = Node.Field(CustomObjectType)

        me = Field(CustomObjectType)

        def resolve_users(self, info, **kwargs) -> "QuerySet[User]":
            if info.context.user.has_perm(f"{User._meta.app_label}.view_all_users"):
                return CustomObjectType._meta.model.objects.all()
            return CustomObjectType._meta.model.objects.none()

        def resolve_me(self, info, **kwargs) -> "User | None":
            if info.context.user.is_authenticated:
                return info.context.user
            return None

    return UsersQueries


UsersQueries = get_user_queries(UserObjectType)
