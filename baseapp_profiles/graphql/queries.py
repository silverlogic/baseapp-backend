from typing import Optional

import graphene
import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node, get_object_type_for_model

from .object_types import ProfileInvitationPreview

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfilesQueries:
    all_profiles = DjangoFilterConnectionField(get_object_type_for_model(Profile))
    profile = Node.Field(get_object_type_for_model(Profile))
    profile_invitation = graphene.Field(
        get_object_type_for_model(ProfileUserRole),
        token=graphene.String(required=True),
        description=(
            "Look up an invitation by its token so the acceptance page can show the right "
            "screen on load. Returns null when the token matches no invitation. The token is "
            "the authorization (this bypasses the member-only node gate); the org `profile` is "
            "hidden once the invitation has expired."
        ),
    )

    profile_invitation_preview = graphene.Field(
        ProfileInvitationPreview,
        token=graphene.String(required=True),
        description=(
            "Public summary of an invitation for its acceptance page: profile name and image, "
            "invited email and name, inviter, message, role, status (an overdue pending "
            "invitation reads EXPIRED), expiry and whether the invitee must sign in rather "
            "than sign up. Needs no sign-in — the token is the authorization. Null for an "
            "unknown token."
        ),
    )

    def resolve_profile_invitation_preview(
        self, info: graphene.ResolveInfo, token: str
    ) -> "Optional[ProfileInvitationPreview]":
        from baseapp_profiles.services.invitations import lookup_invitation

        invitation = lookup_invitation(token)
        if invitation is None:
            return None
        return ProfileInvitationPreview(
            profile_name=invitation.profile_name,
            invited_email=invitation.invited_email,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            invited_first_name=invitation.invited_first_name,
            invited_last_name=invitation.invited_last_name,
            inviter_name=invitation.inviter_name or None,
            message=invitation.message,
            profile_image=invitation.profile_image,
            requires_sign_in=invitation.requires_sign_in,
        )

    def resolve_profile_invitation(
        self, info: graphene.ResolveInfo, token: str
    ) -> "Optional[ProfileUserRole]":
        try:
            return ProfileUserRole.objects.get(invitation_token=token)
        except ProfileUserRole.DoesNotExist:
            return None
