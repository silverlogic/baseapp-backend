from collections.abc import Iterable

import strawberry
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from ..filters import FileFilter

File = swapper.load_model("baseapp_files", "File")
FileLazyType = type_for_model(File)


@strawberry.type
class FilesQueries:
    @connection(
        CountedConnection[FileLazyType] | None,
        filterset_class=FileFilter,
        description="Files created by the current user.",
    )
    def my_files(self, info: Info) -> Iterable[Model]:
        if not info.context.user.is_authenticated:
            return File.objects.none()
        # Total ordering: AbstractFile has no Meta.ordering and cursors need a stable order.
        return File.objects.filter(created_by=info.context.user).order_by("-created", "-pk")

    file = typed_node_field(FileLazyType)
