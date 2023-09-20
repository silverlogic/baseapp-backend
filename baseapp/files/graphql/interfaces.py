import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.models import DocumentId

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
        # Get the DocumentId for this object
        content_type = ContentType.objects.get_for_model(self)
        try:
            document_id = DocumentId.objects.get(
                content_type=content_type,
                object_id=self.pk,
            )
            return File.objects.filter(parent=document_id).order_by("-created")
        except DocumentId.DoesNotExist:
            return File.objects.none()
