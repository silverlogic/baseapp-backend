import swapper
from django.contrib.contenttypes.models import ContentType
from graphene import Boolean, Interface
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.models import DocumentId


class FilesInterface(Interface):
    files_count = GenericScalar()
    is_files_enabled = Boolean()
    files = DjangoFilterConnectionField(
        lambda: swapper.load_model("baseapp_files", "File").get_graphql_object_type()
    )

    def resolve_files_count(self, info, **kwargs):
        if hasattr(self, "get_file_target"):
            return self.get_file_target().files_count
        return {"total": 0}

    def resolve_is_files_enabled(self, info, **kwargs):
        if hasattr(self, "get_file_target"):
            return self.get_file_target().is_files_enabled
        return True

    def resolve_files(self, info, **kwargs):
        File = swapper.load_model("baseapp_files", "File")
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


def get_files_interface():
    return FilesInterface
