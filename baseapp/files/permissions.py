from typing import Any, Optional

import swapper
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()

UserType = AbstractBaseUser | AnonymousUser


class FilesPermissionsBackend(BaseBackend):
    def authenticate(self, request, **kwargs) -> None:
        return None

    @staticmethod
    def _can_add_to_target(user_obj: UserType, obj: Optional[Any]) -> bool:
        """Target-level: may this user attach files to `obj`? Default policy
        mirrors comments' add_comment — authenticated and files enabled.
        Projects can override this backend to enforce target ownership."""
        if not obj:
            return False
        from baseapp_core.plugins import shared_services

        service = shared_services.get("files_metadata")
        enabled = service.is_files_enabled(obj) if service else True
        return user_obj.is_authenticated and enabled

    @staticmethod
    def _is_owner_or_has_global(user_obj: UserType, perm: str, obj: Optional[Any]) -> bool:
        """Owner acts on their own file; otherwise fall back to the global perm
        (ModelBackend doesn't grant global perms when an obj is passed)."""
        if not obj:
            return False
        return obj.created_by == user_obj or user_obj.has_perm(perm)

    def has_perm(self, user_obj: UserType, perm: str, obj: Optional[Any] = None) -> bool:
        """Resolve object-level file permissions: ``add_<file>`` (attach to a
        target), ``attach_<file>`` (owner-only), and view/change/delete
        (owner or global perm). Unknown perms return False so other backends
        can decide."""
        if perm == f"{file_app_label}.add_{file_model_name}":
            return self._can_add_to_target(user_obj, obj)

        if perm == f"{file_app_label}.attach_{file_model_name}":
            return bool(obj) and obj.created_by == user_obj

        if perm in (
            f"{file_app_label}.view_{file_model_name}",
            f"{file_app_label}.change_{file_model_name}",
            f"{file_app_label}.delete_{file_model_name}",
        ):
            return self._is_owner_or_has_global(user_obj, perm, obj)

        return False
