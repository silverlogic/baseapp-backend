import swapper
from django.conf import settings
from django.contrib.auth.backends import BaseBackend

RateModel = swapper.load_model("baseapp_ratings", "Rate")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class RatingsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_ratings.add_rate":
            return user_obj.is_authenticated and getattr(obj, "is_ratings_enabled", False)

        if perm == "baseapp_ratings.add_rate_with_profile" and obj:
            return user_obj.has_perm(f"{profile_app_label}.use_profile", obj)

        if perm == "baseapp_ratings.view_rate":
            return True

        if perm == "baseapp_ratings.list_ratings":
            CAN_ANONYMOUS_VIEW_RATINGS = getattr(
                settings, "BASEAPP_RATINGS_CAN_ANONYMOUS_VIEW_RATINGS", True
            )
            if not CAN_ANONYMOUS_VIEW_RATINGS and not user_obj.is_authenticated:
                return False
            return True

        if perm in ["baseapp_ratings.change_rate", "baseapp_ratings.delete_rate"]:
            if isinstance(obj, RateModel):
                if obj.target and not getattr(obj.target, "is_ratings_enabled", True):
                    return False

                if user_obj.is_authenticated:
                    # Owner can change or delete their own reactions
                    if obj.user_id == user_obj.id:
                        return True

                    # Anyone with permission can change and delete any reaction
                    return user_obj.has_perm(perm)
