import swapper
from graphene import Field
from graphene_django.debug import DjangoDebug

from baseapp_core.graphql.errors import Errors

File = swapper.load_model("baseapp_files", "File")
FileObjectType = File.get_graphql_object_type()


class FilesMutations(object):
    # file_attach_to_target = FileAttachMutation.Field()
