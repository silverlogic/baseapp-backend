import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField

File = swapper.load_model("baseapp_files", "File")
FileObjectType = File.get_graphql_object_type()


class FilesInterface(graphene.Interface):
    files_count = GenericScalar()
    files = DjangoFilterConnectionField(lambda: FileObjectType)

    def resolve_files(self, info, **kwargs):
        parent_content_type = ContentType.objects.get_for_model(self)
        return File.objects.filter(
            parent_content_type=parent_content_type,
            parent_object_id=self.pk,
        ).order_by("-created")
