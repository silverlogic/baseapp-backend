import swapper
from django.contrib.auth.backends import BaseBackend

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label
profile_user_role_app_label = ProfileUserRole._meta.app_label


class ProfilesPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == f"{profile_app_label}.view_profile":
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

        if perm in [f"{profile_app_label}.change_profile", f"{profile_app_label}.delete_profile"]:
            if user_obj.is_authenticated and isinstance(obj, Profile):
                # Owner can change and delete their own profiles
                if obj.owner_id == user_obj.id:
                    return True

                # Anyone with permission can change and delete any profile
                return user_obj.has_perm(perm)

        if perm == f"{profile_app_label}.use_profile" and obj:
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id or obj.members.filter(user_id=user_obj.id).exists()
                )

        if perm == f"{profile_app_label}.delete_profile" and obj:
            if isinstance(obj, Profile):
                return obj.owner_id == user_obj.id

        if perm == f"{profile_app_label}.view_profile_members" and obj:
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id
                    or user_obj.is_superuser
                    or obj.members.filter(user_id=user_obj.id).exists()
                )

        if (
            perm
            in [
                f"{profile_user_role_app_label}.change_profileuserrole",
                f"{profile_user_role_app_label}.delete_profileuserrole",
            ]
            and obj
        ):
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id
                    or obj.members.filter(
                        user_id=user_obj.id, role=ProfileUserRole.ProfileRoles.ADMIN
                    ).exists()
                )
