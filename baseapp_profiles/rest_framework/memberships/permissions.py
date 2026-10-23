import swapper
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_app_label = Profile._meta.app_label
profile_user_role_app_label = ProfileUserRole._meta.app_label


def get_current_profile(request: Request) -> "Profile | None":
    return getattr(request.user, "current_profile", None)


class HasCurrentProfile(BasePermission):
    """The request names a profile the user may act as (see `CurrentProfileMixin`)."""

    message = _("Choose a profile you belong to with the Current-Profile header.")

    def has_permission(self, request: Request, view: APIView) -> bool:
        return get_current_profile(request) is not None


class _CurrentProfilePermission(BasePermission):
    """Checks `perm` against the current profile through the permission backends."""

    perm: str = ""

    def has_permission(self, request: Request, view: APIView) -> bool:
        profile = get_current_profile(request)
        return profile is not None and request.user.has_perm(self.perm, profile)


class CanViewProfileMembers(_CurrentProfilePermission):
    perm = f"{profile_app_label}.view_profile_members"


class CanViewProfileInvitations(_CurrentProfilePermission):
    perm = f"{profile_app_label}.view_profile_invitations"


class CanAddProfileMembers(_CurrentProfilePermission):
    perm = f"{profile_user_role_app_label}.add_profileuserrole"


class CanChangeProfileMembers(_CurrentProfilePermission):
    perm = f"{profile_user_role_app_label}.change_profileuserrole"


class CanDeleteProfileMembers(_CurrentProfilePermission):
    perm = f"{profile_user_role_app_label}.delete_profileuserrole"
