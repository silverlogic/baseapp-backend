import swapper
from django.contrib.auth.backends import BaseBackend

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class ReactionsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_reactions.add_reaction":
            return user_obj.is_authenticated and getattr(obj, "is_reactions_enabled", False)

        if perm == "baseapp_reactions.view_reaction":
            # Anyone can view a reaction
            return True

        if perm in ["baseapp_reactions.change_reaction", "baseapp_reactions.delete_reaction"]:
            if isinstance(obj, Reaction):
                if obj.target and not getattr(obj.target, "is_reactions_enabled", True):
                    return False

                if user_obj.is_authenticated:
                    # Owner can change or delete their own reactions
                    if obj.user_id == user_obj.id:
                        return True

                    # Anyone with permission can change and delete any reaction
                    return user_obj.has_perm(perm)

        if perm == "baseapp_reactions.add_reaction_with_profile" and obj:
            return user_obj.has_perm(f"{profile_app_label}.use_profile", obj)
