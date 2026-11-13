from typing import Any

from django.utils.translation import gettext_lazy as _
from graphene import ID, Field, InputObjectType, relay
from graphene_django.debug import DjangoDebug

from .decorators import login_required
from .errors import Errors
from .utils import get_obj_from_relay_id


def _input_declaration(input_type: type[InputObjectType]) -> type:
    """A plain `Input` class with the fields of an already generated mutation input type."""
    fields = {
        name: field
        for name, field in input_type._meta.fields.items()
        if name != "client_mutation_id"
    }
    return type("Input", (), fields)


class RelayMutation(relay.ClientIDMutation):
    """Relay mutation with `errors` and `_debug`.

    A concrete mutation can be subclassed, for example to add input fields with
    `class Input(ParentMutation.Input)` and keep the GraphQL names with `Meta.name`. Graphene alone
    can't build an input type on top of the one it generated for the parent.
    """

    errors = Errors()
    debug = Field(DjangoDebug, name="_debug")

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, **options: Any) -> None:
        input_class = cls.__dict__.get("Input", getattr(cls, "Input", None))
        if isinstance(input_class, type) and issubclass(input_class, InputObjectType):
            cls.Input = _input_declaration(input_class)
        super().__init_subclass_with_meta__(**options)


class DeleteNode(RelayMutation):
    class Input:
        id = ID(required=True)

    deletedID = ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "DeleteNode":
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
