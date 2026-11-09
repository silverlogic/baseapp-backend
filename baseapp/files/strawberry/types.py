from typing import Any

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_auth.strawberry.permissions import PermissionsInterface
from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import Node, django_type
from baseapp_core.strawberry.enums import choices_enum
from baseapp_core.strawberry.fields import FileInterface, build_thumbnail_url
from baseapp_core.strawberry.scalars import BigInt, JSONString

from ..filters import FileFilter
from ..storage import files_storage, files_storage_is_private
from ..thumbnails import private_thumbnail_name

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()
FileUploadStatusEnum = choices_enum(File, "upload_status")


def can_view_file(info: Info, file_obj: Model) -> bool:
    return info.context.user.has_perm(f"{file_app_label}.view_{file_model_name}", file_obj)


@strawberry_django.type(File, name="AbstractFile")
class AbstractFileType:
    created: strawberry.auto
    modified: strawberry.auto
    file_content_type: strawberry.auto
    file_name: strawberry.auto
    file_size: BigInt | None
    name: strawberry.auto
    description: strawberry.auto
    upload_status: FileUploadStatusEnum
    upload_id: strawberry.auto
    upload_storage_name: strawberry.auto
    total_parts: strawberry.auto
    uploaded_parts: JSONString | None
    upload_expires_at: strawberry.auto
    pk: int | None = strawberry_django.field()

    @strawberry_django.field(only=["file"])
    def file(self, info: Info) -> str:
        return str(self.file) if self.file else ""

    @strawberry_django.field(only=["parent_id"], select_related=["parent__content_type"])
    def parent(self, info: Info) -> Node | None:
        # Graphene returned the DocumentId row, which no Node type can represent.
        return self.parent.content_object if self.parent else None

    @strawberry_django.field(only=["file"])
    def url(self, info: Info) -> str | None:
        """Signed and expiring on private storage; None for viewers without `view_file`."""
        if not can_view_file(info, self):
            return None
        if not self.file:
            return getattr(self, "url", None)
        return info.context.build_absolute_uri(self.file.url)

    @strawberry_django.field(only=["file"])
    def thumbnail(self, info: Info, width: int, height: int) -> str | None:
        """Public storage: shared thumbnail. Private storage: signed URL of a private thumbnail."""
        if not can_view_file(info, self) or not self.file:
            return None
        if not files_storage_is_private():
            return build_thumbnail_url(self.file, info, width, height)
        name = private_thumbnail_name(self.file, width, height)
        return info.context.build_absolute_uri(files_storage.url(name)) if name else None

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if node is not None and not can_view_file(info, node):
            return None
        return node


def file_interfaces() -> tuple[type, ...]:
    return (
        PermissionsInterface,
        FileInterface,
        *strawberry_shared_interfaces.get("CommentsInterface", "ReactionsInterface"),
        Node,
    )


@django_type(File, filterset_class=FileFilter, relations="__all__", only=["created_by_id"])
class FileType(AbstractFileType, *file_interfaces()):
    pass
