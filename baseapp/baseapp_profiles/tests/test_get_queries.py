import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import URLPathFactory

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_app_label = Profile._meta.app_label

GET_PROFILE_BY_PATH = """
    query Profile($id: ID!) {
        profile(id: $id) {
            id
            name
            metadata {
                metaTitle
                metaOgImage(width: 100, height: 100) {
                    url
                }
            }
        }
    }
"""

SEARCH_PROFILES_BY_QUERY_PARAM = """
    query AllProfiles($q: String!) {
        allProfiles(q: $q) {
            edges {
                node {
                    id
                }
            }
        }
    }
"""


def test_profile_metadata(graphql_user_client, image_djangofile):
    profile = ProfileFactory(image=image_djangofile)

    response = graphql_user_client(GET_PROFILE_BY_PATH, variables={"id": profile.relay_id})
    content = response.json()
    assert content["data"]["profile"]["id"] == profile.relay_id
    assert content["data"]["profile"]["name"] == profile.name
    assert content["data"]["profile"]["metadata"]["metaTitle"] == profile.name
    assert content["data"]["profile"]["metadata"]["metaOgImage"]["url"].startswith("http") is True


def test_owner_can_change_profile(django_user_client, graphql_user_client):
    response = graphql_user_client(
        query=f"""
            query Profile($id: ID!) {{
                profile(id: $id) {{
                    canChange: hasPerm(perm: "change")
                    canDelete: hasPerm(perm: "delete")
                    canChangeFull: hasPerm(perm: "{profile_app_label}.change_profile")
                    canDeleteFull: hasPerm(perm: "{profile_app_label}.delete_profile")
                }}
            }}
        """,
        variables={"id": django_user_client.user.profile.relay_id},
    )

    content = response.json()

    assert content["data"]["profile"]["canChange"]
    assert content["data"]["profile"]["canDelete"]
    assert content["data"]["profile"]["canChangeFull"]
    assert content["data"]["profile"]["canDeleteFull"]


def test_another_user_cant_change_profile(graphql_user_client):
    profile = ProfileFactory()

    response = graphql_user_client(
        query=f"""
            query Profile($id: ID!) {{
                profile(id: $id) {{
                    canChange: hasPerm(perm: "change")
                    canDelete: hasPerm(perm: "delete")
                    canChangeFull: hasPerm(perm: "{profile_app_label}.change_profile")
                    canDeleteFull: hasPerm(perm: "{profile_app_label}.delete_profile")
                }}
            }}
        """,
        variables={"id": profile.relay_id},
    )

    content = response.json()

    assert not content["data"]["profile"]["canChange"]
    assert not content["data"]["profile"]["canDelete"]
    assert not content["data"]["profile"]["canChangeFull"]
    assert not content["data"]["profile"]["canDeleteFull"]


def test_owner_can_view_members(django_user_client, graphql_user_client):
    response = graphql_user_client(
        query="""
            query Profile($id: ID!) {
                profile(id: $id) {
                    members {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": django_user_client.user.profile.relay_id},
    )

    content = response.json()

    assert content["data"]["profile"]["members"]


def test_another_user_cant_view_members(graphql_user_client):
    profile = ProfileFactory()

    response = graphql_user_client(
        query="""
            query Profile($id: ID!) {
                profile(id: $id) {
                    members {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": profile.relay_id},
    )

    content = response.json()

    assert content["data"]["profile"]["members"]


def test_members_ordered_by_status(django_user_client, graphql_user_client):
    user = django_user_client.user
    profile = ProfileFactory(owner=user)
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.INACTIVE,
    )

    response = graphql_user_client(
        query="""
            query Profile($id: ID!, $orderBy: String) {
                profile(id: $id) {
                    members(orderBy: $orderBy) {
                        edges {
                            node {
                                id
                                status
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": profile.relay_id, "orderBy": "status"},
    )

    content = response.json()

    members = content["data"]["profile"]["members"]["edges"]
    statuses = [member["node"]["status"] for member in members]

    assert statuses == ["PENDING", "INACTIVE", "ACTIVE", "ACTIVE"]


def test_members_not_ordered_by_status(django_user_client, graphql_user_client):
    user = django_user_client.user
    profile = ProfileFactory(owner=user)
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.INACTIVE,
    )

    response = graphql_user_client(
        query="""
            query Profile($id: ID!) {
                profile(id: $id) {
                    members {
                        edges {
                            node {
                                id
                                status
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": profile.relay_id},
    )

    content = response.json()

    members = content["data"]["profile"]["members"]["edges"]
    statuses = [member["node"]["status"] for member in members]

    assert statuses == ["ACTIVE", "PENDING", "ACTIVE", "INACTIVE"]


def test_search_profiles(graphql_user_client):
    profile1 = ProfileFactory(name="David")
    profile2 = ProfileFactory(name="Daniel")
    profile3 = ProfileFactory(name="Mark")
    profile4 = ProfileFactory(name="John")
    profile5 = ProfileFactory(name="Donald")
    urlPath1 = URLPathFactory(path="danger.john", is_active=True, language=None)
    profile_content_type = ContentType.objects.get_for_model(Profile)
    urlPath1.target_content_type = profile_content_type
    urlPath1.target_object_id = profile4.id
    urlPath1.save()
    urlPath1.refresh_from_db()
    profile4.refresh_from_db()

    response = graphql_user_client(SEARCH_PROFILES_BY_QUERY_PARAM, variables={"q": "da"})
    content = response.json()
    profiles = [
        id for id in [edge["node"]["id"] for edge in content["data"]["allProfiles"]["edges"]]
    ]
    assert profile1.relay_id in profiles
    assert profile2.relay_id in profiles
    assert profile3.relay_id not in profiles
    assert profile4.relay_id in profiles
    assert profile5.relay_id not in profiles


def test_search_members_filters_by_name(django_user_client, graphql_user_client):
    user = django_user_client.user
    profile = ProfileFactory(owner=user)
    p1 = ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )

    response = graphql_user_client(
        query="""
            query Profile($id: ID!, $q: String) {
                profile(id: $id) {
                    members(q: $q) {
                        edges {
                            node {
                                id
                                status
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": profile.relay_id, "q": p1.user.first_name},
    )

    content = response.json()
    members = content["data"]["profile"]["members"]["edges"]
    assert len(members) == 1
    assert members[0]["node"]["status"] == "ACTIVE"


def test_search_members_filters_by_last_name(django_user_client, graphql_user_client):
    django_user_client.user.last_name = "Owner"
    django_user_client.user.save()
    user = django_user_client.user
    profile = ProfileFactory(owner=user)
    p1 = ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
        user=UserFactory(last_name="Member"),
    )
    p1.user.refresh_from_db()
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )

    response = graphql_user_client(
        query="""
            query Profile($id: ID!, $q: String) {
                profile(id: $id) {
                    members(q: $q) {
                        edges {
                            node {
                                id
                                status
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": profile.relay_id, "q": p1.user.last_name},
    )

    content = response.json()
    members = content["data"]["profile"]["members"]["edges"]

    assert len(members) == 1
    assert members[0]["node"]["status"] == "ACTIVE"


def test_search_members_returns_all_members_if_empty_query(django_user_client, graphql_user_client):
    user = django_user_client.user
    profile = ProfileFactory(owner=user)
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    )
    ProfileUserRoleFactory(
        profile=profile,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )
    response = graphql_user_client(
        query="""
            query Profile($id: ID!, $q: String) {
                profile(id: $id) {
                    members(q: $q) {
                        edges {
                            node {
                                id
                                status
                            }
                        }
                    }
                }
            }
        """,
        variables={"id": profile.relay_id, "q": ""},
    )
    content = response.json()
    members = content["data"]["profile"]["members"]["edges"]
    assert len(members) == 2
