import graphene
from graphene import relay


class PermissionsInterface(relay.Node):
    has_perm = graphene.Boolean(perm=graphene.String(required=True))

    def resolve_has_perm(self, info, perm, **kwargs):
        if "." not in perm:
            # Builds a permission string of the form "<app_label>.<perm>_<model_name>"
            opts = self._meta
            codename = "%s_%s" % (perm, opts.model_name)
            perm = "%s.%s" % (opts.app_label, codename)

        return info.context.user.has_perm(perm, self)
