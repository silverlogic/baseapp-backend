import graphene
import swapper
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from graphql_relay.connection.arrayconnection import offset_to_cursor

from baseapp_core.graphql import RelayMutation, get_obj_from_relay_id, login_required
from baseapp_core.models import DocumentId

from .interfaces import FilesInterface

File = swapper.load_model("baseapp_files", "File")
app_label = File._meta.app_label
file_model_name = File._meta.model_name
FileObjectType = File.get_graphql_object_type()


class FileAttachToTarget(RelayMutation):
    """
    Attach one or more files to a target object.

    Usage:
        mutation {
            fileAttachToTarget(input: {
                fileRelayIds: ["RmlsZU9iamVjdFR5cGU6MQ==", "RmlsZU9iamVjdFR5cGU6Mg=="]
                targetObjectId: "Q29tbWVudE9iamVjdFR5cGU6MQ=="
            }) {
                attachedFiles {
                    node {
                        id
                        fileName
                    }
                }
                target {
                    ... on CommentsInterface {
                        filesCount
                        isFilesEnabled
                    }
                }
            }
        }
    """

    attached_files = graphene.List(
        graphene.NonNull(FileObjectType._meta.connection.Edge),
        required=True,
    )
    target = graphene.Field(FilesInterface, required=True)

    class Input:
        file_relay_ids = graphene.List(graphene.ID, required=True)
        target_object_id = graphene.ID(required=True)

    @classmethod
    @login_required
    @transaction.atomic
    def mutate_and_get_payload(cls, root, info, **input):
        from django.contrib.contenttypes.models import ContentType

        file_relay_ids = input.get("file_relay_ids", [])
        target_object_id = input.get("target_object_id")

        if not file_relay_ids:
            raise GraphQLError(
                str(_("At least one file must be provided")),
                extensions={"code": "invalid_input"},
            )

        # Get the target object
        target = get_obj_from_relay_id(info, target_object_id)
        if not target:
            raise GraphQLError(
                str(_("Target object not found")),
                extensions={"code": "not_found"},
            )

        # Get or create DocumentId for the target
        target_content_type = ContentType.objects.get_for_model(target)
        target_document_id, created = DocumentId.objects.get_or_create(
            content_type=target_content_type,
            object_id=target.pk,
        )

        # Check if files are enabled for this target
        if hasattr(target, "get_file_target"):
            file_target = target.get_file_target()
            if not file_target.is_files_enabled:
                raise GraphQLError(
                    str(_("Files are not enabled for this target")),
                    extensions={"code": "files_disabled"},
                )

        # Get all files and verify ownership
        files = []
        for file_relay_id in file_relay_ids:
            file_obj = get_obj_from_relay_id(info, file_relay_id)
            if not file_obj:
                raise GraphQLError(
                    str(_("File not found: {file_id}")).format(file_id=file_relay_id),
                    extensions={"code": "not_found"},
                )

            # Check ownership - only file owner can attach it
            if file_obj.created_by != info.context.user:
                raise GraphQLError(
                    str(_("You don't have permission to attach this file")),
                    extensions={"code": "permission_required"},
                )

            # Check if file is already attached to another parent
            if file_obj.parent_id:
                raise GraphQLError(
                    str(_("File {file_name} is already attached to another object")).format(
                        file_name=file_obj.file_name
                    ),
                    extensions={"code": "already_attached"},
                )

            files.append(file_obj)

        # Attach all files to the target
        for file_obj in files:
            # TO DO: Check permission
            # if not info.context.user.has_perm("baseapp_files.attach_file", file_obj):
            file_obj.parent = target_document_id
            file_obj.save(update_fields=["parent"])

        # Refresh target to get updated files_count
        target.refresh_from_db()

        # Create file edges for response
        attached_files = [
            FileObjectType._meta.connection.Edge(node=file_obj, cursor=offset_to_cursor(i))
            for i, file_obj in enumerate(files)
        ]

        return FileAttachToTarget(attached_files=attached_files, target=target)


class FileDelete(RelayMutation):
    deleted_id = graphene.ID()
    parent = graphene.Field(FilesInterface)

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        relay_id = input.get("id")

        error_exception = GraphQLError(
            str(_("You don't have permission to perform this action")),
            extensions={"code": "permission_required"},
        )

        obj = get_obj_from_relay_id(info, relay_id)
        if not obj:
            raise error_exception

        if not info.context.user.has_perm(f"{app_label}.delete_{file_model_name}", obj):
            raise error_exception

        parent = obj.parent.content_object if obj.parent else None

        obj.delete()

        return FileDelete(deleted_id=relay_id, parent=parent)


class FilesMutations(object):
    file_attach_to_target = FileAttachToTarget.Field()
    file_delete = FileDelete.Field()
