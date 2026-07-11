import swapper
from django.contrib.contenttypes.models import ContentType
from graphene import Boolean, Interface
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.plugins import shared_services

from ..utils import default_files_count


class FilesInterface(Interface):
    files_count = GenericScalar()
    is_files_enabled = Boolean()
    files = DjangoFilterConnectionField(
        lambda: swapper.load_model("baseapp_files", "File").get_graphql_object_type()
    )

    def resolve_files_count(self, info, **kwargs) -> dict:
        if service := shared_services.get("files_metadata"):
            return service.get_files_count(self)
        return default_files_count()

    def resolve_is_files_enabled(self, info, **kwargs) -> bool:
        if service := shared_services.get("files_metadata"):
            return service.is_files_enabled(self)
        return True

    def resolve_files(self, info, **kwargs):
        File = swapper.load_model("baseapp_files", "File")

        service = shared_services.get("files_metadata")
        if service is not None and not service.is_files_enabled(self):
            return File.objects.none()

        # Filter through the DocumentId join instead of fetching the DocumentId
        # row per object — keeps the connection a single query per list.
        content_type = ContentType.objects.get_for_model(self)
        return File.objects.filter(
            parent__content_type=content_type,
            parent__object_id=self.pk,
        ).order_by("-created")


def get_files_interface():
    return FilesInterface
