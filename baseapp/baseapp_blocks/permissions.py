import swapper
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

Block = swapper.load_model("baseapp_blocks", "Block")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label
User = get_user_model()


class BlocksPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_blocks.add_block_with_profile":
            return user_obj.has_perm(f"{profile_app_label}.use_profile", obj)

        if perm == "baseapp_blocks.add_block":
            return user_obj.is_authenticated

        if (
            perm
            in ["baseapp_blocks.view_block-blockers_count", "baseapp_blocks.view_block-blockers"]
            and obj
        ):
            # person with permission can view a blockers, usually will be admin or moderators
            return user_obj.has_perm(perm)

        if perm in [
            "baseapp_blocks.view_block-blocking_count",
            "baseapp_blocks.view_block-blocking",
        ]:
            if isinstance(obj, Block):
                # Owner or users with permission can view
                return (
                    obj.user_id == user_obj.id
                    or user_obj.has_perm(f"{profile_app_label}.use_profile", obj.actor)
                    or user_obj.has_perm(perm)
                )
            elif isinstance(obj, Profile):
                # Owner or users with permission can view
                return (
                    obj.owner_id == user_obj.id
                    or user_obj.has_perm(f"{profile_app_label}.use_profile", obj)
                    or user_obj.has_perm(perm)
                )

        if perm in ["baseapp_blocks.delete_block"]:
            if isinstance(obj, Block):
                if obj.user_id == user_obj.id:
                    return True

                # Anyone with permission can change and delete any block
                return user_obj.has_perm(
                    "baseapp_profiles.use_profile", obj.actor
                ) or user_obj.has_perm(perm)
