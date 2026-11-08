import strawberry
import swapper
from strawberry import UNSET

from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as g
from .interfaces import FilesInterface

File = swapper.load_model("baseapp_files", "File")
FileLazyType = type_for_model(File)


@strawberry.input(name="FileAttachToTargetInput")
class FileAttachToTargetInput(RelayMutationInput):
    file_relay_ids: list[strawberry.ID | None]
    target_object_id: strawberry.ID
    upload_tokens: list[str] | None = UNSET


@strawberry.type(name="FileAttachToTargetPayload")
class FileAttachToTargetPayload(RelayMutationPayload):
    attached_files: list[Edge[FileLazyType]]
    target: FilesInterface


@strawberry.input(name="FileDeleteInput")
class FileDeleteInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="FileDeletePayload")
class FileDeletePayload(RelayMutationPayload):
    deleted_id: strawberry.ID | None = None
    parent: FilesInterface | None = None


@strawberry.type
class FilesMutations:
    file_attach_to_target = graphene_relay_mutation(
        g.FileAttachToTarget, FileAttachToTargetInput, FileAttachToTargetPayload
    )
    file_delete = graphene_relay_mutation(g.FileDelete, FileDeleteInput, FileDeletePayload)
