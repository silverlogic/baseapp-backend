from typing import Any, Optional

import swapper
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

UserType = AbstractBaseUser | AnonymousUser


class GeoPermissionsBackend(BaseBackend):
    def authenticate(self, request, **kwargs) -> None:
        return None

    @staticmethod
    def _is_owner_or_has_global(user_obj: UserType, perm: str, obj: Optional[Any]) -> bool:
        """Owner acts on their own feature; otherwise fall back to the global perm
        (ModelBackend doesn't grant global perms when an obj is passed)."""
        if not obj or not user_obj.is_authenticated:
            return False
        # created_by is nullable and AnonymousUser.pk is None, so the authentication
        # guard above is what stops an unowned feature from matching every anonymous user.
        return obj.created_by_id == user_obj.pk or user_obj.has_perm(perm)

    def has_perm(self, user_obj: UserType, perm: str, obj: Optional[Any] = None) -> bool:
        GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")
        app_label = GeoJSONFeature._meta.app_label

        if perm == f"{app_label}.view_geojsonfeature":
            return True

        if perm == f"{app_label}.add_geojsonfeature":
            return user_obj.is_authenticated

        if perm in (
            f"{app_label}.change_geojsonfeature",
            f"{app_label}.delete_geojsonfeature",
        ):
            # With no obj this returns False so ModelBackend still decides the global
            # grant; with an obj the creator is allowed and everyone else needs it.
            return self._is_owner_or_has_global(user_obj, perm, obj)

        return False
