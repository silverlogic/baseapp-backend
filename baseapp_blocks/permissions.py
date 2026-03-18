import swapper
from django.apps import apps
from django.contrib.auth.backends import BaseBackend

Block = swapper.load_model("baseapp_blocks", "Block")


class BlocksPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if apps.is_installed("baseapp_profiles"):
            return self._has_perm_with_profiles(user_obj, perm, obj)
        return self._has_perm_without_profiles(user_obj, perm, obj)

    def _has_perm_with_profiles(self, user_obj, perm, obj=None):
        Profile = swapper.load_model("baseapp_profiles", "Profile")

        profile_app_label = Profile._meta.app_label
        use_profile_perm = f"{profile_app_label}.use_profile"

        if perm == "baseapp_blocks.add_block_with_profile":
            return bool(obj and user_obj.has_perm(use_profile_perm, obj))

        if perm == "baseapp_blocks.add_block":
            return user_obj.is_authenticated

        if (
            perm
            in ["baseapp_blocks.view_block-blockers_count", "baseapp_blocks.view_block-blockers"]
            and obj
        ):
            # person with permission can view blockers, usually admin/moderators
            return user_obj.has_perm(perm)

        if perm in [
            "baseapp_blocks.view_block-blocking_count",
            "baseapp_blocks.view_block-blocking",
        ]:
            if isinstance(obj, Block):
                actor = getattr(obj, "actor", None)
                return (
                    obj.user_id == user_obj.id
                    or (actor and user_obj.has_perm(use_profile_perm, actor))
                    or user_obj.has_perm(perm)
                )

            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id
                    or user_obj.has_perm(use_profile_perm, obj)
                    or user_obj.has_perm(perm)
                )

        if perm == "baseapp_blocks.delete_block" and isinstance(obj, Block):
            if obj.user_id == user_obj.id:
                return True
            actor = getattr(obj, "actor", None)
            return (actor and user_obj.has_perm(use_profile_perm, actor)) or user_obj.has_perm(perm)

        return False

    def _has_perm_without_profiles(self, user_obj, perm, obj=None):
        if perm == "baseapp_blocks.add_block":
            return user_obj.is_authenticated

        if (
            perm
            in ["baseapp_blocks.view_block-blockers_count", "baseapp_blocks.view_block-blockers"]
            and obj
        ):
            return user_obj.has_perm(perm)

        if perm in [
            "baseapp_blocks.view_block-blocking_count",
            "baseapp_blocks.view_block-blocking",
        ] and isinstance(obj, Block):
            return obj.user_id == user_obj.id or user_obj.has_perm(perm)

        if perm == "baseapp_blocks.delete_block" and isinstance(obj, Block):
            if obj.user_id == user_obj.id:
                return True
            return user_obj.has_perm(perm)

        return False
