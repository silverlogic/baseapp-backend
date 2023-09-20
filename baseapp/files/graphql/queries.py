import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node

File = swapper.load_model("baseapp_files", "File")
FileObjectType = File.get_graphql_object_type()


class FilesQueries:
    my_files = DjangoFilterConnectionField(FileObjectType)
    file = Node.Field(FileObjectType)
