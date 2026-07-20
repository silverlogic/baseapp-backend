import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.auth.backends import BaseBackend

from baseapp_core.plugins import shared_services

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


def _is_reactions_enabled(obj) -> bool:
    if service := shared_services.get("reactable_metadata"):
        return service.is_reactions_enabled(obj)
    return False


def can_anonymous_view_reactions() -> bool:
    """Resolve `BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONS`, falling back to
    the original double-S typo'd name for back-compat (drop in a future release)."""
    return getattr(
        settings,
        "BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONS",
        getattr(settings, "BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONSS", True),
    )


class ReactionsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None) -> bool:
        if apps.is_installed("baseapp_profiles"):
            return self._has_perm_with_profiles(user_obj, perm, obj)
        return self._has_perm_with_user(user_obj, perm, obj)

    def _has_perm_with_profiles(self, user_obj, perm, obj=None) -> bool:
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        use_profile_perm = f"{Profile._meta.app_label}.use_profile"

        if perm == "baseapp_reactions.add_reaction":
            return user_obj.is_authenticated and _is_reactions_enabled(obj)

        if perm == "baseapp_reactions.view_reaction":
            if not can_anonymous_view_reactions() and not user_obj.is_authenticated:
                return False
            return True

        if perm in ["baseapp_reactions.change_reaction", "baseapp_reactions.delete_reaction"]:
            if isinstance(obj, Reaction):
                if obj.target and not _is_reactions_enabled(obj.target):
                    return False

                if user_obj.is_authenticated:
                    # Owner can change or delete their own reactions
                    if obj.user_id == user_obj.id:
                        return True

                    # Anyone with permission can change and delete any reaction
                    return user_obj.has_perm(perm)

        if perm == "baseapp_reactions.add_reaction_with_profile" and obj:
            return user_obj.has_perm(use_profile_perm, obj)

        return False

    def _has_perm_with_user(self, user_obj, perm, obj=None) -> bool:
        if perm == "baseapp_reactions.add_reaction":
            return user_obj.is_authenticated and _is_reactions_enabled(obj)

        if perm == "baseapp_reactions.view_reaction":
            if not can_anonymous_view_reactions() and not user_obj.is_authenticated:
                return False
            return True

        if perm in ["baseapp_reactions.change_reaction", "baseapp_reactions.delete_reaction"]:
            if isinstance(obj, Reaction):
                if obj.target and not _is_reactions_enabled(obj.target):
                    return False

                if user_obj.is_authenticated:
                    if obj.user_id == user_obj.id:
                        return True
                    return user_obj.has_perm(perm)

        return False
