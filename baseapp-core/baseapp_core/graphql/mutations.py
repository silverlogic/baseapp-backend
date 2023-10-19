from graphene import Field, relay
from graphene_django.debug import DjangoDebug

from .errors import Errors


class RelayMutation(relay.ClientIDMutation):
    errors = Errors()
    debug = Field(DjangoDebug, name="_debug")

    class Meta:
        abstract = True
