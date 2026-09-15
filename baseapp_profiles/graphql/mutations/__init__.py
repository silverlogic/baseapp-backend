from .invitations import (
    ProfileAcceptInvitation,
    ProfileCancelInvitation,
    ProfileDeclineInvitation,
    ProfileResendInvitation,
    ProfileSendInvitation,
)
from .profiles import (
    BaseProfileSerializer,
    ProfileCreate,
    ProfileCreateSerializer,
    ProfileDelete,
    ProfileUpdate,
    ProfileUpdateSerializer,
)
from .roles import (
    ProfileUserRoleCreate,
    ProfileUserRoleDelete,
    ProfileUserRoleUpdate,
)


class ProfilesMutations(object):
    profile_create = ProfileCreate.Field()
    profile_update = ProfileUpdate.Field()
    profile_delete = ProfileDelete.Field()
    profile_user_role_create = ProfileUserRoleCreate.Field()
    profile_user_role_update = ProfileUserRoleUpdate.Field()
    profile_user_role_delete = ProfileUserRoleDelete.Field()
    profile_send_invitation = ProfileSendInvitation.Field()
    profile_accept_invitation = ProfileAcceptInvitation.Field()
    profile_decline_invitation = ProfileDeclineInvitation.Field()
    profile_cancel_invitation = ProfileCancelInvitation.Field()
    profile_resend_invitation = ProfileResendInvitation.Field()


__all__ = [
    "ProfilesMutations",
    "BaseProfileSerializer",
    "ProfileCreate",
    "ProfileCreateSerializer",
    "ProfileUpdate",
    "ProfileUpdateSerializer",
    "ProfileDelete",
    "ProfileUserRoleCreate",
    "ProfileUserRoleUpdate",
    "ProfileUserRoleDelete",
    "ProfileSendInvitation",
    "ProfileAcceptInvitation",
    "ProfileDeclineInvitation",
    "ProfileCancelInvitation",
    "ProfileResendInvitation",
]
