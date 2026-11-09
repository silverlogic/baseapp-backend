import strawberry
import swapper
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge, offset_to_cursor
from baseapp_core.strawberry.mutations import relay_mutation

from ..base import FileableModel
from ..permissions import anonymous_uploads_allowed
from ..tokens import bind_upload_tokens
from .interfaces import FilesInterface

File = swapper.load_model("baseapp_files", "File")
FileLazyType = type_for_model(File)
app_label = File._meta.app_label
file_model_name = File._meta.model_name

ATTACH_DESCRIPTION = """
    Attach one or more files to a target object.

    Usage:
        mutation {
            fileAttachToTarget(input: {
                fileRelayIds: ["RmlsZU9iamVjdFR5cGU6MQ==", "RmlsZU9iamVjdFR5cGU6Mg=="]
                targetObjectId: "Q29tbWVudE9iamVjdFR5cGU6MQ=="
                # Only for anonymous uploads: the tokens returned when they started.
                uploadTokens: ["..."]
            }) {
                attachedFiles {
                    node {
                        id
                        fileName
                    }
                }
                target {
                    ... on FilesInterface {
                        filesCount
                        isFilesEnabled
                    }
                }
            }
        }
    """


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


def _error(message: str, code: str) -> GraphQLError:
    return GraphQLError(message, extensions={"code": code})


def _already_attached(file_obj: File) -> GraphQLError:
    return _error(
        str(_("File {file_name} is already attached to another object")).format(
            file_name=file_obj.file_name
        ),
        "already_attached",
    )


def _file_not_found(file_relay_id: str) -> GraphQLError:
    return _error(str(_("File not found: {file_id}")).format(file_id=file_relay_id), "not_found")


@transaction.atomic
def attach_to_target(info: Info, input: FileAttachToTargetInput) -> FileAttachToTargetPayload:
    file_relay_ids = input.file_relay_ids or []
    upload_tokens = input.upload_tokens if input.upload_tokens is not UNSET else None
    bind_upload_tokens(info.context.user, upload_tokens)

    if not file_relay_ids:
        raise _error(str(_("At least one file must be provided")), "invalid_input")

    target = get_obj_from_relay_id(info, input.target_object_id)
    if not target:
        raise _error(str(_("Target object not found")), "not_found")

    # Only FileableModel targets resolve as FilesInterface in the payload.
    if not isinstance(target, FileableModel):
        raise _error(str(_("This object does not support file attachments")), "invalid_target")

    if service := shared_services.get("files_metadata"):
        if not service.is_files_enabled(target):
            raise _error(str(_("Files are not enabled for this target")), "files_disabled")
    if not info.context.user.has_perm(f"{app_label}.add_{file_model_name}", target):
        raise _error(
            str(_("You don't have permission to attach files to this object")),
            "permission_required",
        )

    files = []
    for file_relay_id in file_relay_ids:
        file_obj = get_obj_from_relay_id(info, file_relay_id)
        if not isinstance(file_obj, File):
            raise _file_not_found(file_relay_id)
        if not info.context.user.has_perm(f"{app_label}.attach_{file_model_name}", file_obj):
            raise _error(
                str(_("You don't have permission to attach this file")), "permission_required"
            )
        if file_obj.parent_id:
            raise _already_attached(file_obj)
        files.append(file_obj)

    # Lock and re-check: unclaimed-upload cleanup locks the same rows.
    locked = File.objects.select_for_update().in_bulk([file_obj.pk for file_obj in files])
    for index, file_obj in enumerate(files):
        current = locked.get(file_obj.pk)
        if current is None:
            raise _file_not_found(file_relay_ids[index])
        if current.parent_id:
            raise _already_attached(current)
        files[index] = current

    target_document_id = DocumentId.get_or_create_for_object(target)
    for file_obj in files:
        file_obj.parent = target_document_id
        file_obj.save(update_fields=["parent"])

    target.refresh_from_db()

    return FileAttachToTargetPayload(
        attached_files=[
            Edge(node=file_obj, cursor=offset_to_cursor(i)) for i, file_obj in enumerate(files)
        ],
        target=target,
    )


@strawberry.type
class FilesMutations:
    @relay_mutation(description=ATTACH_DESCRIPTION)
    def file_attach_to_target(
        self, info: Info, input: FileAttachToTargetInput
    ) -> FileAttachToTargetPayload | None:
        user = info.context.user
        if not (user.is_authenticated or anonymous_uploads_allowed()):
            raise _error(str(_("authentication required")), "authentication_required")
        return attach_to_target(info, input)

    @relay_mutation(login_required=True)
    def file_delete(self, info: Info, input: FileDeleteInput) -> FileDeletePayload | None:
        error = _error(
            str(_("You don't have permission to perform this action")), "permission_required"
        )

        obj = get_obj_from_relay_id(info, input.id)
        if not obj:
            raise error
        if not info.context.user.has_perm(f"{app_label}.delete_{file_model_name}", obj):
            raise error

        parent = obj.parent.content_object if obj.parent else None
        obj.delete()

        return FileDeletePayload(deleted_id=input.id, parent=parent)
