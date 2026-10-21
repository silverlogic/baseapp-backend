import swapper
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Exists, OuterRef

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label
profile_user_role_app_label = ProfileUserRole._meta.app_label


def is_active_member(
    profile: Profile, user_obj: AbstractBaseUser | AnonymousUser, role: int | None = None
) -> bool:
    """
    Whether `user_obj` holds an ACTIVE membership of `profile`.

    A membership that is PENDING, INACTIVE, DECLINED or EXPIRED grants nothing: a
    deactivated member stops reaching the profile on their very next request, and an
    invitee reaches nothing until they accept. Pass `role` to also require a role.
    """
    if not user_obj.is_authenticated:
        return False

    members = profile.members.filter(
        user_id=user_obj.id, status=ProfileUserRole.ProfileRoleStatus.ACTIVE
    )
    if role is not None:
        members = members.filter(role=role)
    return members.exists()


def active_membership_subquery(user_obj: AbstractBaseUser | AnonymousUser) -> Exists:
    """
    `Exists()` subquery matching profiles `user_obj` is an ACTIVE member of.

    Used instead of a `members__user` join so that filtering a Profile queryset by
    membership neither duplicates rows nor needs `.distinct()`.
    """
    return Exists(
        ProfileUserRole.objects.filter(
            profile_id=OuterRef("pk"),
            user_id=user_obj.id,
            status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
        )
    )


class ProfilesPermissionsBackend(BaseBackend):
    def has_perm(
        self, user_obj: AbstractBaseUser | AnonymousUser, perm: str, obj: Profile | None = None
    ) -> bool | None:
        if perm == f"{profile_app_label}.view_profile":
            if not obj:
                # Anyone can view a profile
                return True
            elif isinstance(obj, Profile):
                if obj.status == Profile.ProfileStatus.PUBLIC:
                    return True
                else:
                    return obj.owner_id == user_obj.id or is_active_member(obj, user_obj)

        if perm in [f"{profile_app_label}.change_profile", f"{profile_app_label}.delete_profile"]:
            if user_obj.is_authenticated and isinstance(obj, Profile):
                # Owner can change and delete their own profiles
                if obj.owner_id == user_obj.id:
                    return True

                # Anyone with permission can change and delete any profile
                return user_obj.has_perm(perm)

        if perm == f"{profile_app_label}.use_profile" and obj:
            if isinstance(obj, Profile):
                return obj.owner_id == user_obj.id or is_active_member(obj, user_obj)

        if perm == f"{profile_app_label}.delete_profile" and obj:
            if isinstance(obj, Profile):
                return obj.owner_id == user_obj.id

        if perm == f"{profile_app_label}.view_profile_members" and obj:
            if isinstance(obj, Profile):
                return (
                    obj.owner_id == user_obj.id
                    or user_obj.is_superuser
                    or is_active_member(obj, user_obj)
                )

        if (
            perm
            in [
                f"{profile_user_role_app_label}.add_profileuserrole",
                f"{profile_user_role_app_label}.change_profileuserrole",
                f"{profile_user_role_app_label}.delete_profileuserrole",
            ]
            and obj
        ):
            if isinstance(obj, Profile):
                return obj.owner_id == user_obj.id or is_active_member(
                    obj, user_obj, role=ProfileUserRole.ProfileRoles.ADMIN
                )
