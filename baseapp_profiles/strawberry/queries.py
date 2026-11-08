from typing import Any, Optional

import strawberry
import swapper
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from ..graphql.filters import ProfileFilter

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ProfileLazyType = type_for_model(Profile)


@strawberry.type
class ProfilesQueries:
    all_profiles = connection(
        CountedConnection[ProfileLazyType] | None, filterset_class=ProfileFilter
    )
    profile = typed_node_field(ProfileLazyType)

    @strawberry.field(
        graphql_type=Optional[type_for_model(ProfileUserRole)],
        description=(
            "Look up an invitation by its token so the acceptance page can show the right "
            "screen on load. Returns null when the token matches no invitation. The token is "
            "the authorization (this bypasses the member-only node gate); the org `profile` is "
            "hidden once the invitation has expired."
        ),
    )
    def profile_invitation(self, info: Info, token: str) -> Any:
        try:
            return ProfileUserRole.objects.get(invitation_token=token)
        except ProfileUserRole.DoesNotExist:
            return None
