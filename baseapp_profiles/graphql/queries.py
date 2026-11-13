from typing import TYPE_CHECKING, Optional

import graphene
import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node, get_object_type_for_model
from baseapp_profiles.discoverability import filter_discoverable_profiles

if TYPE_CHECKING:
    from django.db.models import QuerySet

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

    def resolve_all_profiles(self, info: graphene.ResolveInfo, **kwargs) -> "QuerySet[Profile]":
        # Narrows the list only. The connection still applies ProfileObjectType.get_queryset
        # and the filterset on top, and node(id) / nested profile fields never pass through here.
        return filter_discoverable_profiles(Profile._default_manager.all(), info.context.user)

    def resolve_profile_invitation(
        self, info: graphene.ResolveInfo, token: str
    ) -> "Optional[ProfileUserRole]":
        try:
            return ProfileUserRole.objects.get(invitation_token=token)
        except ProfileUserRole.DoesNotExist:
            return None
