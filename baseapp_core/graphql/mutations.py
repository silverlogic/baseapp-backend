from django.utils.translation import gettext_lazy as _
from graphene import ID, Field, relay
from graphene_django.debug import DjangoDebug

from .decorators import login_required
from .errors import Errors
from .utils import get_obj_from_relay_id


class RelayMutation(relay.ClientIDMutation):
    errors = Errors()
    debug = Field(DjangoDebug, name="_debug")

    class Meta:
        abstract = True


class DeleteNode(RelayMutation):
    class Input:
        id = ID(required=True)

    deletedID = ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        relay_id = input.get("id")
        obj = get_obj_from_relay_id(info, relay_id)

        error_exception = PermissionError(_("You don't have permission to delete this."))
        if not obj:
            raise error_exception

        opts = obj._meta
        codename = "delete_%s" % opts.model_name

        if not info.context.user.has_perm("%s.%s" % (opts.app_label, codename), obj):
            raise error_exception

        obj.delete()

        return DeleteNode(deletedID=relay_id)
