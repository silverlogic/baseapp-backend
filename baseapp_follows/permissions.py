import swapper
from django.apps import apps
from django.contrib.auth.backends import BaseBackend

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if apps.is_installed("baseapp_profiles"):
            return self._has_perm_with_profiles(user_obj, perm, obj)
        return self._has_perm_with_user(user_obj, perm, obj)

    def _has_perm_with_profiles(self, user_obj, perm, obj=None):
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        use_profile_perm = f"{Profile._meta.app_label}.use_profile"

        if perm == "baseapp_follows.add_follow":
            # TO DO: check if not blocked?
            return user_obj.is_authenticated
        if perm == "baseapp_follows.add_follow_with_profile":
            return user_obj.has_perm(use_profile_perm, obj)
        if perm == "baseapp_follows.delete_follow":
            if isinstance(obj, Follow):
                return obj.user_id == user_obj.id or user_obj.has_perm(use_profile_perm, obj.actor)

        return False

    def _has_perm_with_user(self, user_obj, perm, obj=None):
        if perm == "baseapp_follows.add_follow":
            return user_obj.is_authenticated

        if perm == "baseapp_follows.delete_follow" and isinstance(obj, Follow):
            return obj.user_id == user_obj.id or user_obj.has_perm(perm)

        return False
