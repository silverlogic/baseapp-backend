import swapper
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from rest_framework.exceptions import PermissionDenied, ValidationError

from baseapp_core.models import DocumentId

from ..base import FileableModel

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()

UserType = AbstractBaseUser | AnonymousUser


def enforce_can_attach_to_parent(user: UserType, parent_document_pk: int) -> None:
    """
    Authorize attaching a file to the object behind ``parent_document_pk`` (a
    ``DocumentId`` pk). Mirrors the ``FileAttachToTarget`` GraphQL mutation so
    the REST upload/set-parent paths cannot bypass target-level authorization:
    the target must opt into files (``FileableModel``) and the user must hold
    the ``add_<file_model>`` permission on it.
    """
    try:
        document = DocumentId.objects.get(pk=parent_document_pk)
    except DocumentId.DoesNotExist:
        raise ValidationError(["Invalid parent: target not found."]) from None

    target = document.content_object
    if not isinstance(target, FileableModel):
        raise ValidationError(["This object does not support file attachments."])

    if not user.has_perm(f"{file_app_label}.add_{file_model_name}", target):
        raise PermissionDenied("You don't have permission to attach files to this object.")
