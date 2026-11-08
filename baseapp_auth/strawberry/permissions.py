import strawberry
from django.utils.translation import gettext_lazy as _
from strawberry.types import Info

from baseapp_auth.utils.normalize_permission import normalize_permission
from baseapp_core.strawberry import Node


@strawberry.interface(name="PermissionsInterface")
class PermissionsInterface(Node):
    @strawberry.field(
        description=str(
            _("Determine if the logged in user has a specific permission for this object.")
        )
    )
    def has_perm(self, info: Info, perm: str) -> bool | None:
        return info.context.user.has_perm(normalize_permission(perm, self), self)
