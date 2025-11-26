import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")
FileObjectType = File.get_graphql_object_type()


class FilesInterface(graphene.Interface):
    files_count = GenericScalar()
    is_files_enabled = graphene.Boolean()
    files = DjangoFilterConnectionField(lambda: FileObjectType)

    def resolve_files_count(self, info, **kwargs):
        if hasattr(self, "get_file_target"):
            return self.get_file_target().files_count
        return {"total": 0}

    def resolve_is_files_enabled(self, info, **kwargs):
        if hasattr(self, "get_file_target"):
            return self.get_file_target().is_files_enabled
        return True

    def resolve_files(self, info, **kwargs):
        parent_content_type = ContentType.objects.get_for_model(self)
        return File.objects.filter(
            parent_content_type=parent_content_type,
            parent_object_id=self.pk,
        ).order_by("-created")
