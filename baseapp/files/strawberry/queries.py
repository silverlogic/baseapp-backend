from collections.abc import Iterable

import strawberry
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from ..graphql.object_types import FileFilter
from ..graphql.queries import FilesQueries as GrapheneFilesQueries

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
        return GrapheneFilesQueries.resolve_my_files(None, info)

    file = typed_node_field(FileLazyType)
