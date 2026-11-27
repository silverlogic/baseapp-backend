"""
`urlPath(path:).target` must apply the same visibility rule as `profile(id:)`:
a private profile is only returned to its owner, its active members and superusers.
"""

import pytest
import swapper
from django.test import Client

from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import URLPathFactory

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

PROFILE_PATH = "/some-handle"

GET_PROFILE_BY_URL_PATH = """
    query ProfileByPath($path: String!) {
        urlPath(path: $path) {
            path
            target {
                __typename
                ... on Profile {
                    id
                    name
                }
            }
        }
    }
"""


def _make_profile(status: int, **kwargs) -> Profile:
    profile = ProfileFactory(name="Secret Name", status=status, **kwargs)
    URLPathFactory(target=profile, path=PROFILE_PATH, language=None, is_active=True)
    return profile


def _target_for(client: Client, path: str = PROFILE_PATH) -> dict | None:
    response = graphql_query(GET_PROFILE_BY_URL_PATH, variables={"path": path}, client=client)
    content = response.json()
    assert "errors" not in content
    return content["data"]["urlPath"]["target"]


def _client_for(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_anon_can_view_public_profile_by_url_path(django_client) -> None:
    profile = _make_profile(Profile.ProfileStatus.PUBLIC)

    target = _target_for(django_client)

    assert target == {"__typename": "Profile", "id": profile.relay_id, "name": "Secret Name"}


def test_anon_cant_view_private_profile_by_url_path(django_client) -> None:
    _make_profile(Profile.ProfileStatus.PRIVATE)

    assert _target_for(django_client) is None


def test_another_user_cant_view_private_profile_by_url_path(django_user_client) -> None:
    _make_profile(Profile.ProfileStatus.PRIVATE)

    assert _target_for(django_user_client) is None


@pytest.mark.parametrize(
    "member_status",
    [
        ProfileUserRole.ProfileRoleStatus.PENDING,
        ProfileUserRole.ProfileRoleStatus.INACTIVE,
        ProfileUserRole.ProfileRoleStatus.DECLINED,
        ProfileUserRole.ProfileRoleStatus.EXPIRED,
    ],
)
def test_non_active_member_cant_view_private_profile_by_url_path(
    django_user_client, member_status
) -> None:
    profile = _make_profile(Profile.ProfileStatus.PRIVATE)
    ProfileUserRoleFactory(profile=profile, user=django_user_client.user, status=member_status)

    assert _target_for(django_user_client) is None


def test_owner_can_view_private_profile_by_url_path(django_user_client) -> None:
    profile = _make_profile(Profile.ProfileStatus.PRIVATE, owner=django_user_client.user)

    target = _target_for(django_user_client)

    assert target["id"] == profile.relay_id


def test_active_member_can_view_private_profile_by_url_path(django_user_client) -> None:
    profile = _make_profile(Profile.ProfileStatus.PRIVATE)
    ProfileUserRoleFactory(
        profile=profile,
        user=django_user_client.user,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )

    target = _target_for(django_user_client)

    assert target["id"] == profile.relay_id


def test_superuser_can_view_private_profile_by_url_path() -> None:
    profile = _make_profile(Profile.ProfileStatus.PRIVATE)
    superuser = UserFactory(is_superuser=True)

    target = _target_for(_client_for(superuser))

    assert target["id"] == profile.relay_id


def test_anon_cant_view_private_profile_by_inactive_url_path(django_client) -> None:
    # An old path is followed to the target's active one; neither may expose the profile.
    profile = ProfileFactory(name="Secret Name", status=Profile.ProfileStatus.PRIVATE)
    URLPathFactory(target=profile, path="/old-handle", language="en", is_active=False)
    URLPathFactory(target=profile, path="/new-handle", language="en", is_active=True)

    response = graphql_query(
        GET_PROFILE_BY_URL_PATH, variables={"path": "/old-handle"}, client=django_client
    )
    content = response.json()

    assert content["data"]["urlPath"]["path"] == "/new-handle"
    assert content["data"]["urlPath"]["target"] is None


def test_url_path_and_node_agree_on_private_profile(django_user_client) -> None:
    profile = _make_profile(Profile.ProfileStatus.PRIVATE)

    response = graphql_query(
        """
            query ProfileById($id: ID!) {
                profile(id: $id) {
                    id
                }
            }
        """,
        variables={"id": profile.relay_id},
        client=django_user_client,
    )

    assert response.json()["data"]["profile"] is None
    assert _target_for(django_user_client) is None
