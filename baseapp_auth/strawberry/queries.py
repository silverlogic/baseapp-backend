from collections.abc import Iterable
from typing import Any, Optional

import strawberry
from django.contrib.auth import get_user_model
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from ..graphql.filters import UsersFilter

User = get_user_model()
UserLazyType = type_for_model(User)


@strawberry.type
class UsersQueries:
    @connection(CountedConnection[UserLazyType] | None, filterset_class=UsersFilter)
    def users(self, info: Info) -> Iterable[Model]:
        if info.context.user.has_perm(f"{User._meta.app_label}.view_all_users"):
            return User.objects.all()
        return User.objects.none()

    user = typed_node_field(UserLazyType)

    @strawberry.field(graphql_type=Optional[UserLazyType])
    def me(self, info: Info) -> Any:
        if info.context.user.is_authenticated:
            return info.context.user
        return None
