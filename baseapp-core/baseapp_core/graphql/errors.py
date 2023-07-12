import graphene
from graphene_django.types import ErrorType


def Errors():
    return graphene.List(ErrorType)
