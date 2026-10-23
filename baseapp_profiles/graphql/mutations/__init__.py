from .base import ExtensibleMutation
from .invitations import (
    ProfileAcceptInvitation,
    ProfileAcceptInvitationWithSignup,
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
    ProfileMemberDeactivate,
    ProfileMemberReactivate,
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
    profile_member_deactivate = ProfileMemberDeactivate.Field()
    profile_member_reactivate = ProfileMemberReactivate.Field()
    profile_send_invitation = ProfileSendInvitation.Field()
    profile_accept_invitation = ProfileAcceptInvitation.Field()
    profile_accept_invitation_with_signup = ProfileAcceptInvitationWithSignup.Field()
    profile_decline_invitation = ProfileDeclineInvitation.Field()
    profile_cancel_invitation = ProfileCancelInvitation.Field()
    profile_resend_invitation = ProfileResendInvitation.Field()


__all__ = [
    "ProfilesMutations",
    "ExtensibleMutation",
    "BaseProfileSerializer",
    "ProfileCreate",
    "ProfileCreateSerializer",
    "ProfileUpdate",
    "ProfileUpdateSerializer",
    "ProfileDelete",
    "ProfileUserRoleCreate",
    "ProfileUserRoleUpdate",
    "ProfileUserRoleDelete",
    "ProfileMemberDeactivate",
    "ProfileMemberReactivate",
    "ProfileSendInvitation",
    "ProfileAcceptInvitation",
    "ProfileAcceptInvitationWithSignup",
    "ProfileDeclineInvitation",
    "ProfileCancelInvitation",
    "ProfileResendInvitation",
]
