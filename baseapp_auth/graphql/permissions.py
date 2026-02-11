import graphene
from django.utils.translation import gettext_lazy as _

from baseapp_auth.utils.normalize_permission import normalize_permission
from baseapp_core.graphql import Node as RelayNode


class PermissionsInterface(RelayNode):
    has_perm = graphene.Boolean(
        perm=graphene.String(required=True),
        description=_("Determine if the logged in user has a specific permission for this object."),
    )

    def resolve_has_perm(self, info, perm, **kwargs):
        # Builds a permission string of the form "<app_label>.<perm>_<model_name>"
        perm = normalize_permission(perm, self)
        return info.context.user.has_perm(perm, self)
