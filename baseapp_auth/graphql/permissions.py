import graphene
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import Node as RelayNode


class PermissionsInterface(RelayNode):
    has_perm = graphene.Boolean(
        perm=graphene.String(required=True),
        description=_("Determine if the logged in user has a specific permission for this object."),
    )

    def resolve_has_perm(self, info, perm, **kwargs):
        # Builds a permission string of the form "<app_label>.<perm>_<model_name>"
        if "." not in perm:
            opts = self._meta
            if "_" not in perm:
                codename = "%s_%s" % (perm, opts.model_name)
            else:
                codename = perm
            perm = "%s.%s" % (opts.app_label, codename)

        return info.context.user.has_perm(perm, self)
