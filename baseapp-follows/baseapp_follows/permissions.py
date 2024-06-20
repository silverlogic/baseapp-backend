import swapper
from django.contrib.auth.backends import BaseBackend

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_follows.add_follow":
            # TO DO: check if not blocked?
            return user_obj.is_authenticated
        if perm == "baseapp_follows.add_follow_with_profile":
            return user_obj.has_perm("baseapp_profiles.use_profile", obj)
        if perm == "baseapp_follows.delete_follow":
            if isinstance(obj, Follow):
                return obj.user_id == user_obj.id or user_obj.has_perm(
                    "baseapp_profiles.use_profile", obj.actor
                )
