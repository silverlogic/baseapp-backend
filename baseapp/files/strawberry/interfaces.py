from collections.abc import Iterable
from typing import Any

import strawberry
import strawberry_django
import swapper
from django.contrib.contenttypes.models import ContentType
from django.db.models import BooleanField, Model, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, model_from_info, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.scalars import GenericScalar

from ..graphql.interfaces import FilesInterface as GrapheneFilesInterface
from ..graphql.object_types import FileFilter

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")


def _file_target(info: Info) -> Any:
    content_type_id = ContentType.objects.get_for_model(model_from_info(info)).pk
    return FileTarget.objects.filter(
        target__content_type_id=content_type_id, target__object_id=OuterRef("pk")
    )


# Same annotations as FileTarget.annotate_queryset, attached only when the field is selected.
def _files_count_annotation(info: Info) -> Any:
    return Subquery(_file_target(info).values("files_count")[:1])


def _is_files_enabled_annotation(info: Info) -> Any:
    return Coalesce(
        Subquery(_file_target(info).values("is_files_enabled")[:1], output_field=BooleanField()),
        Value(True),
    )


@strawberry.interface(name="FilesInterface")
class FilesInterface:
    @strawberry_django.field(annotate={"_file_target_files_count": _files_count_annotation})
    def files_count(self, info: Info) -> GenericScalar | None:
        return GrapheneFilesInterface.resolve_files_count(self, info)

    @strawberry_django.field(
        annotate={"_file_target_is_files_enabled": _is_files_enabled_annotation}
    )
    def is_files_enabled(self, info: Info) -> bool | None:
        return GrapheneFilesInterface.resolve_is_files_enabled(self, info)

    @connection(CountedConnection[type_for_model(File)] | None, filterset_class=FileFilter)
    def files(self, info: Info) -> Iterable[Model]:
        return GrapheneFilesInterface.resolve_files(self, info)
