"""
Query-count tests for the profiles operations the web app reads most.

Each test pins today's behaviour; none of them fixes anything. Lists use
`assert_queries_dont_grow`; the single profile uses `assert_max_queries`. Where a list grows with
the data today, the test declares the measured `per_item` and names BE-5b, which removes the
N+1 and lowers the bound to 0. A declared bound still fails if the list gets worse.
"""

import pytest

from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
from baseapp_core.tests.factories import UserFactory

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

PROFILE_PAGE_QUERY = """
    query ProfilePage($id: ID!) {
        profile(id: $id) {
            id
            name
            image(width: 100, height: 100)
            bannerImage(width: 100, height: 100)
            followersCount
            followingCount
            isFollowedByMe
        }
    }
"""

ALL_PROFILES_QUERY = """
    query AllProfiles {
        allProfiles {
            edges {
                node {
                    id
                    name
                    image(width: 48, height: 48)
                }
            }
        }
    }
"""

PROFILE_SWITCHER_QUERY = """
    query ProfileSwitcher {
        me {
            profiles {
                edges {
                    node {
                        id
                        name
                        image(width: 48, height: 48)
                    }
                }
            }
        }
    }
"""

MEMBERS_QUERY = """
    query ProfileMembers($id: ID!) {
        profile(id: $id) {
            members {
                edges {
                    node {
                        id
                        role
                        status
                        user {
                            id
                        }
                    }
                }
            }
        }
    }
"""

PROFILE_PAGE_HINT = (
    "ProfileObjectType.pre_optimization_hook lost one of the commentable / followable / "
    "reportable annotations, or a count field stopped reading it"
)


def current_profile_headers(profile) -> dict[str, str]:
    return {"HTTP_CURRENT_PROFILE": profile.relay_id}


def test_profile_page_as_anonymous(graphql_client) -> None:
    profile = ProfileFactory()

    with assert_max_queries(5, hint=PROFILE_PAGE_HINT):
        response = graphql_client(PROFILE_PAGE_QUERY, variables={"id": profile.relay_id})

    content = response.json()
    assert "errors" not in content, content
    assert content["data"]["profile"]["name"] == profile.name
    assert content["data"]["profile"]["isFollowedByMe"] is False


def test_profile_page_with_current_profile(graphql_user_client, django_user_client) -> None:
    profile = ProfileFactory()
    current_profile = django_user_client.user.profile

    with assert_max_queries(12, hint=PROFILE_PAGE_HINT):
        response = graphql_user_client(
            PROFILE_PAGE_QUERY,
            variables={"id": profile.relay_id},
            headers=current_profile_headers(current_profile),
        )

    content = response.json()
    assert "errors" not in content, content
    assert content["data"]["profile"]["name"] == profile.name
    assert content["data"]["profile"]["isFollowedByMe"] is False


def test_all_profiles_dont_grow(graphql_client) -> None:
    owner = UserFactory()

    assert_queries_dont_grow(
        run=lambda: graphql_client(ALL_PROFILES_QUERY),
        add_items=lambda n: ProfileFactory.create_batch(n, owner=owner),
        # Accepted for now: one DocumentId lookup per profile (its public id), because the
        # connection skips the optimizer. BE-5b removes it and lowers this to 0.
        per_item=1,
        hint="allProfiles is a DjangoFilterConnectionField, which skips the query optimizer",
    )


def test_profile_switcher_dont_grow(graphql_user_client, django_user_client) -> None:
    user = django_user_client.user

    assert_queries_dont_grow(
        run=lambda: graphql_user_client(PROFILE_SWITCHER_QUERY),
        add_items=lambda n: ProfileUserRoleFactory.create_batch(n, user=user),
        # Accepted for now: one DocumentId lookup per profile (its public id), because the
        # connection skips the optimizer. BE-5b removes it and lowers this to 0.
        per_item=1,
        hint="me.profiles is a DjangoFilterConnectionField, which skips the query optimizer",
    )


def test_members_dont_grow(graphql_user_client, django_user_client) -> None:
    profile = django_user_client.user.profile

    assert_queries_dont_grow(
        run=lambda: graphql_user_client(
            MEMBERS_QUERY,
            variables={"id": profile.relay_id},
            headers=current_profile_headers(profile),
        ),
        add_items=lambda n: ProfileUserRoleFactory.create_batch(n, profile=profile),
        hint=(
            "members reverted to a resolver without select_related, or resolve_members started "
            "querying per row"
        ),
    )


def test_members_are_hidden_from_non_members(graphql_user_client) -> None:
    profile = ProfileFactory()
    ProfileUserRoleFactory.create_batch(3, profile=profile)

    with assert_max_queries(15):
        response = graphql_user_client(MEMBERS_QUERY, variables={"id": profile.relay_id})

    content = response.json()
    assert "errors" not in content, content
    assert content["data"]["profile"]["members"]["edges"] == []
