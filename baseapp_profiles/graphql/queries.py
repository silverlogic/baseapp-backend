from typing import Optional

import graphene
import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node, get_object_type_for_model

from .object_types import ProfileInvitationObjectType

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfilesQueries:
    all_profiles = DjangoFilterConnectionField(get_object_type_for_model(Profile))
    profile = Node.Field(get_object_type_for_model(Profile))
    profile_invitation = graphene.Field(
        ProfileInvitationObjectType,
        token=graphene.String(required=True),
        description=(
            "Look up an invitation's current state by its token, so the acceptance page can "
            "show the right screen on load. Returns null when the token matches no invitation. "
            "The token itself is the authorization."
        ),
    )

    def resolve_profile_invitation(
        self, info: graphene.ResolveInfo, token: str
    ) -> Optional[ProfileInvitationObjectType]:
        try:
            invitation = ProfileUserRole.objects.get(invitation_token=token)
        except ProfileUserRole.DoesNotExist:
            return None

        is_expired = invitation.is_invitation_expired()
        # Report the effective status without persisting it — a query must stay side-effect
        # free; the accept/decline mutations are responsible for writing EXPIRED.
        status = ProfileUserRole.ProfileRoleStatus.EXPIRED if is_expired else invitation.status
        # Only expose the profile (name/avatar/banner for the acceptance page) while the
        # invitation is still valid — never leak it for an expired link.
        profile = None if is_expired else invitation.profile
        return ProfileInvitationObjectType(status=status, is_expired=is_expired, profile=profile)
