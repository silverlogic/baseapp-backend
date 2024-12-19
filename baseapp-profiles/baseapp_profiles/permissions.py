import swapper
from django.contrib.auth.backends import BaseBackend

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfilesPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_profiles.view_profile":
            if not obj:
                # Anyone can view a profile
                return True
            elif isinstance(obj, Profile):
                if obj.status == Profile.ProfileStatus.PUBLIC:
                    return True
                else:
                    return (
                        obj.owner_id == user_obj.id
                        or obj.members.filter(user_id=user_obj.id).exists()
                    )

        if perm in ["baseapp_profiles.change_profile", "baseapp_profiles.delete_profile"]:
            if user_obj.is_authenticated and isinstance(obj, Profile):
                # Owner can change and delete their own profiles
                if obj.owner_id == user_obj.id:
                    return True

                # Anyone with permission can change and delete any profile
                return user_obj.has_perm(perm)

        if perm == "baseapp_profiles.use_profile" and obj:
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id or obj.members.filter(user_id=user_obj.id).exists()
                )

        if perm == "baseapp_profiles.delete_profile" and obj:
            if isinstance(obj, Profile):
                return obj.owner_id == user_obj.id

        if perm == "baseapp_profiles.view_profile_members" and obj:
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id
                    or user_obj.is_superuser
                    or obj.members.filter(user_id=user_obj.id).exists()
                )

        if perm == "baseapp_profiles.change_profileuserrole" and obj:
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id
                    or obj.members.filter(
                        user_id=user_obj.id, role=ProfileUserRole.ProfileRoles.ADMIN
                    ).exists()
                )
