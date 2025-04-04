import graphene
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType


def Errors():
    return graphene.List(
        ErrorType, description=_("May contain more than one error for same field.")
    )
