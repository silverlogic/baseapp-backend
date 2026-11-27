"""The profile switcher (`me.profiles`) offers only profiles the user can act as."""

import pytest
import swapper

from .factories import ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Status = ProfileUserRole.ProfileRoleStatus

SWITCHER = """
    query MyProfiles {
        me { profiles { edges { node { id } } } }
    }
"""


def test_the_switcher_lists_owned_profiles_and_active_memberships(
    django_user_client, graphql_user_client
) -> None:
    user = django_user_client.user
    owned = user.profile
    active = ProfileUserRoleFactory(user=user).profile
    for status in (Status.PENDING, Status.DECLINED, Status.INACTIVE, Status.EXPIRED):
        ProfileUserRoleFactory(user=user, status=status)
    # Others' memberships of the user's own profile do not duplicate it.
    ProfileUserRoleFactory(profile=owned)
    ProfileUserRoleFactory(profile=owned)

    content = graphql_user_client(SWITCHER).json()
    ids = [edge["node"]["id"] for edge in content["data"]["me"]["profiles"]["edges"]]

    assert sorted(ids) == sorted([owned.relay_id, active.relay_id])
