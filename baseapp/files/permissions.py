from typing import Any, Optional

import swapper
from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

from .storage import files_storage_is_private

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()

UserType = AbstractBaseUser | AnonymousUser


def anonymous_uploads_allowed() -> bool:
    """Whether anonymous callers may upload and attach files (``BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS``)."""
    return bool(getattr(settings, "BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS", False))


class FilesPermissionsBackend(BaseBackend):
    """
    Object-level permissions for files. Every rule is a small method so a project can
    subclass this backend and override just the one it needs (the template does, in
    ``apps/files/permissions.py``).
    """

    def authenticate(self, request, **kwargs) -> None:
        return None

    @staticmethod
    def _can_upload(user_obj: UserType) -> bool:
        """May this user upload a file not tied to a target yet (``add_<file>`` without an
        object)? Default: authenticated users, and anyone while
        ``BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS`` is on. Checked before an upload starts."""
        return user_obj.is_authenticated or anonymous_uploads_allowed()

    @staticmethod
    def _can_add_to_target(user_obj: UserType, obj: Optional[Any]) -> bool:
        """Target-level: may this user attach files to `obj`? Default policy
        mirrors comments' add_comment — authenticated and files enabled; anonymous
        callers too when ``BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS`` is on.
        Projects can override this backend to enforce target ownership."""
        if not obj:
            return False
        from baseapp_core.plugins import shared_services

        service = shared_services.get("files_metadata")
        enabled = service.is_files_enabled(obj) if service else True
        return enabled and (user_obj.is_authenticated or anonymous_uploads_allowed())

    @staticmethod
    def _holds_upload_token(user_obj: UserType, obj: Any) -> bool:
        """An anonymous upload's owner: the caller presented its upload token
        (bound by ``bind_upload_tokens``). Only files without a creator qualify."""
        return obj.created_by_id is None and obj.pk in getattr(user_obj, "file_upload_tokens", ())

    @classmethod
    def _is_owner(cls, user_obj: UserType, obj: Any) -> bool:
        return obj.created_by == user_obj or cls._holds_upload_token(user_obj, obj)

    @classmethod
    def _is_owner_or_has_global(cls, user_obj: UserType, perm: str, obj: Optional[Any]) -> bool:
        """Owner acts on their own file; otherwise fall back to the global perm
        (ModelBackend doesn't grant global perms when an obj is passed)."""
        if not obj:
            return False
        return cls._is_owner(user_obj, obj) or user_obj.has_perm(perm)

    @staticmethod
    def _can_view_parent(user_obj: UserType, obj: Any) -> bool:
        """Whoever may view the object a file is attached to may view the file.
        Delegates to that object's own ``view_<model>`` permission."""
        if not obj.parent_id or obj.parent is None:
            return False
        target = obj.parent.content_object
        if target is None:
            return False
        meta = target._meta
        return user_obj.has_perm(f"{meta.app_label}.view_{meta.model_name}", target)

    @classmethod
    def _can_view(cls, user_obj: UserType, perm: str, obj: Optional[Any]) -> bool:
        """
        Who may see a file and get its URL. Public storage: anyone, as before. Private
        storage: the owner (including an anonymous uploader with its token), viewers of
        the object it is attached to, or holders of the global perm (staff).
        """
        if not obj:
            return False
        if not files_storage_is_private():
            return True
        return (
            cls._is_owner(user_obj, obj)
            or cls._can_view_parent(user_obj, obj)
            or user_obj.has_perm(perm)
        )

    def has_perm(self, user_obj: UserType, perm: str, obj: Optional[Any] = None) -> bool:
        """Resolve object-level file permissions: ``add_<file>`` (upload at all, or
        attach to a target when one is given), ``attach_<file>`` (owner-only), ``view_<file>`` (see ``_can_view``),
        and change/delete (owner or global perm). Unknown perms return False so
        other backends can decide."""
        if perm == f"{file_app_label}.add_{file_model_name}":
            if obj is None:
                return self._can_upload(user_obj)
            return self._can_add_to_target(user_obj, obj)

        if perm == f"{file_app_label}.attach_{file_model_name}":
            return bool(obj) and self._is_owner(user_obj, obj)

        if perm == f"{file_app_label}.view_{file_model_name}":
            return self._can_view(user_obj, perm, obj)

        if perm in (
            f"{file_app_label}.change_{file_model_name}",
            f"{file_app_label}.delete_{file_model_name}",
        ):
            return self._is_owner_or_has_global(user_obj, perm, obj)

        return False
