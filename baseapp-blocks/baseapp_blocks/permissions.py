import swapper
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

Block = swapper.load_model("baseapp_blocks", "Block")
User = get_user_model()


class BlocksPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_blocks.as_actor":
            return user_obj == obj

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
                return obj.actor == user_obj or user_obj.has_perm(perm)
            elif isinstance(obj, User):
                # Owner or users with permission can view
                return obj == user_obj or user_obj.has_perm(perm)

        if perm in ["baseapp_blocks.delete_block"]:
            if isinstance(obj, Block):
                if user_obj.is_authenticated and obj.actor and obj.actor == user_obj:
                    return True

                # Anyone with permission can change and delete any block
                return user_obj.has_perm(perm)
