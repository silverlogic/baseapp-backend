from graphene import relay

from .errors import Errors


class RelayMutation(relay.ClientIDMutation):
    errors = Errors()

    class Meta:
        abstract = True
