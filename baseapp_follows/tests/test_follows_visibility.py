"""
`baseapp_follows.view_followers` / `baseapp_follows.view_following` gate the
FollowsInterface lists and counts and `node(id:)` on a Follow. Both default to True;
these tests swap in a backend that makes them private to the profile's members.
"""

import pytest
import swapper
from django.conf import settings
from django.test import override_settings

from baseapp_core.hashids.utils import is_uuid4
from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory
from baseapp_follows.permissions import FollowsPermissionsBackend
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import FollowFactory

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")

pytestmark = pytest.mark.django_db


class PrivateFollowsPermissionsBackend(FollowsPermissionsBackend):
    """Followers / following are visible to the profile's own members only."""

    def has_perm(self, user_obj, perm, obj=None) -> bool | None:
        if perm in ("baseapp_follows.view_followers", "baseapp_follows.view_following"):
            return isinstance(obj, Profile) and user_obj.has_perm(
                f"{Profile._meta.app_label}.use_profile", obj
            )
        return super().has_perm(user_obj, perm, obj)


def _backends_with(backend_cls: type) -> list[str]:
    path = f"{backend_cls.__module__}.{backend_cls.__qualname__}"
    return [
        path if b == "baseapp_follows.permissions.FollowsPermissionsBackend" else b
        for b in settings.AUTHENTICATION_BACKENDS
    ]


PROFILE_FOLLOWS_QUERY = """
    query GetProfile($id: ID!) {
        node(id: $id) {
            ... on FollowsInterface {
                followersCount
                followingCount
                followers { edges { node { id } } }
                following { edges { node { id } } }
            }
        }
    }
"""

FOLLOW_NODE_QUERY = """
    query GetFollow($id: ID!) {
        node(id: $id) {
            id
        }
    }
"""


@pytest.fixture
def follow_graph() -> tuple:
    """`profile` follows `followed` and is followed by `follower`; nobody owns them."""
    profile = ProfileFactory(owner=UserFactory())
    followed = ProfileFactory(owner=UserFactory())
    follower = ProfileFactory(owner=UserFactory())
    following_row = FollowFactory(actor_object=profile, target_object=followed, user=profile.owner)
    follower_row = FollowFactory(actor_object=follower, target_object=profile, user=follower.owner)
    return profile, following_row, follower_row


def test_view_perms_default_to_true(django_user_client) -> None:
    profile = ProfileFactory()
    backend = FollowsPermissionsBackend()
    for user in (django_user_client.user, UserFactory.build(is_active=False)):
        assert backend.has_perm(user, "baseapp_follows.view_followers", profile) is True
        assert backend.has_perm(user, "baseapp_follows.view_following", profile) is True


def test_follows_are_public_by_default(graphql_client, follow_graph) -> None:
    profile, following_row, follower_row = follow_graph

    content = graphql_client(PROFILE_FOLLOWS_QUERY, variables={"id": profile.relay_id}).json()
    node = content["data"]["node"]

    assert node["followersCount"] == 1
    assert node["followingCount"] == 1
    assert [e["node"]["id"] for e in node["followers"]["edges"]] == [follower_row.relay_id]
    assert [e["node"]["id"] for e in node["following"]["edges"]] == [following_row.relay_id]

    for row in (following_row, follower_row):
        content = graphql_client(FOLLOW_NODE_QUERY, variables={"id": row.relay_id}).json()
        assert content["data"]["node"]["id"] == row.relay_id


def test_private_follows_are_hidden_from_others(graphql_user_client, follow_graph) -> None:
    profile, _following_row, _follower_row = follow_graph

    with override_settings(
        AUTHENTICATION_BACKENDS=_backends_with(PrivateFollowsPermissionsBackend)
    ):
        content = graphql_user_client(
            PROFILE_FOLLOWS_QUERY, variables={"id": profile.relay_id}
        ).json()

    assert "errors" not in content, content
    node = content["data"]["node"]
    assert node["followersCount"] is None
    assert node["followingCount"] is None
    assert node["followers"]["edges"] == []
    assert node["following"]["edges"] == []


def test_private_follows_are_hidden_from_anonymous(graphql_client, follow_graph) -> None:
    profile, _following_row, _follower_row = follow_graph

    with override_settings(
        AUTHENTICATION_BACKENDS=_backends_with(PrivateFollowsPermissionsBackend)
    ):
        content = graphql_client(PROFILE_FOLLOWS_QUERY, variables={"id": profile.relay_id}).json()

    node = content["data"]["node"]
    assert node["followersCount"] is None
    assert node["followingCount"] is None
    assert node["followers"]["edges"] == []
    assert node["following"]["edges"] == []


def test_private_follows_are_visible_to_the_profile_owner(
    django_user_client, graphql_user_client
) -> None:
    profile = ProfileFactory(owner=django_user_client.user)
    followed = ProfileFactory(owner=UserFactory())
    follower = ProfileFactory(owner=UserFactory())
    following_row = FollowFactory(actor_object=profile, target_object=followed, user=profile.owner)
    follower_row = FollowFactory(actor_object=follower, target_object=profile, user=follower.owner)

    with override_settings(
        AUTHENTICATION_BACKENDS=_backends_with(PrivateFollowsPermissionsBackend)
    ):
        content = graphql_user_client(
            PROFILE_FOLLOWS_QUERY, variables={"id": profile.relay_id}
        ).json()

    node = content["data"]["node"]
    assert node["followersCount"] == 1
    assert node["followingCount"] == 1
    assert [e["node"]["id"] for e in node["followers"]["edges"]] == [follower_row.relay_id]
    assert [e["node"]["id"] for e in node["following"]["edges"]] == [following_row.relay_id]


def test_follow_node_is_hidden_when_both_sides_are_private(
    graphql_user_client, follow_graph
) -> None:
    _profile, following_row, follower_row = follow_graph

    with override_settings(
        AUTHENTICATION_BACKENDS=_backends_with(PrivateFollowsPermissionsBackend)
    ):
        for row in (following_row, follower_row):
            content = graphql_user_client(FOLLOW_NODE_QUERY, variables={"id": row.relay_id}).json()
            assert content["data"]["node"] is None


def test_follow_node_is_visible_from_either_side(django_user_client, graphql_user_client) -> None:
    mine = ProfileFactory(owner=django_user_client.user)
    other = ProfileFactory(owner=UserFactory())
    # Visible through view_following on the actor (my profile follows someone)...
    as_actor = FollowFactory(actor_object=mine, target_object=other, user=mine.owner)
    # ...and through view_followers on the target (someone follows my profile).
    as_target = FollowFactory(actor_object=other, target_object=mine, user=other.owner)

    with override_settings(
        AUTHENTICATION_BACKENDS=_backends_with(PrivateFollowsPermissionsBackend)
    ):
        for row in (as_actor, as_target):
            content = graphql_user_client(FOLLOW_NODE_QUERY, variables={"id": row.relay_id}).json()
            assert content["data"]["node"]["id"] == row.relay_id


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_follow_node_by_public_id_respects_visibility(graphql_user_client, follow_graph) -> None:
    """Clients send public UUIDs, which resolve through the public-id strategy."""
    _profile, following_row, _follower_row = follow_graph
    public_id = str(DocumentId.get_or_create_for_object(following_row).public_id)
    assert is_uuid4(public_id)

    content = graphql_user_client(FOLLOW_NODE_QUERY, variables={"id": public_id}).json()
    assert content["data"]["node"]["id"] == public_id

    with override_settings(
        AUTHENTICATION_BACKENDS=_backends_with(PrivateFollowsPermissionsBackend)
    ):
        content = graphql_user_client(FOLLOW_NODE_QUERY, variables={"id": public_id}).json()

    assert content["data"]["node"] is None
