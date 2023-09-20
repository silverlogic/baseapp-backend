import swapper
from graphene import Field
from graphene_django.debug import DjangoDebug
from graphene_django_cud.mutations import (
    DjangoCreateMutation,
    DjangoDeleteMutation,
    DjangoPatchMutation,
)

from baseapp_core.graphql.errors import Errors

File = swapper.load_model("baseapp_files", "File")
FileObjectType = File.get_graphql_object_type()


class FileCreateMutation(DjangoCreateMutation):
    errors = Errors()
    debug = Field(DjangoDebug, name="_debug")
    file = Field(FileObjectType._meta.connection.Edge)
    # files = Field("files.object_types.FileObjectType", required=False)

    class Meta:
        model = File
        login_required = True
        auto_context_fields = {"user": "user"}
        exclude_fields = ("user", "created", "modified")
        # field_types = {"file_type": NonNull(FileTypeEnum)}


class PatchFileMutation(DjangoPatchMutation):
    class Meta:
        model = File
        login_required = True
        exclude_fields = ("user", "created", "modified")


class DeleteFileMutation(DjangoDeleteMutation):
    class Meta:
        model = File
        login_required = True
        exclude_fields = ("user", "created", "modified")


class FilesMutations(object):
    file_create = FileCreateMutation.Field()
    file_patch = PatchFileMutation.Field()
    file_delete = DeleteFileMutation.Field()
