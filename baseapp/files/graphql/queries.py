from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node

from .object_types import FileObjectType


class FilesQueries:
    my_files = DjangoFilterConnectionField(FileObjectType)
    file = Node.Field(FileObjectType)
