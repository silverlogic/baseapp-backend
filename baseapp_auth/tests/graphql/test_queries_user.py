import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

QUERY = """
    query GetUser($id: ID!) {
        user(id: $id) {
            id
            pk
            isAuthenticated
            email
        }
    }
"""

MALICIOUS_QUERY = """
    query MaliciousLoop {
        users {
            edges {
                node {
                    comments {
                        edges {
                            node {
                                user {
                                    comments {
                                        edges {
                                            node {
                                                user {
                                                    comments {
                                                        edges {
                                                            node {
                                                                id
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
"""

QUERY_USERS_LIST = """
    query GetUsersList {
        users {
            edges {
                node {
                    id
                    firstName
                    lastName
                    profile {
                        id
                        name
                    }
                }
            }
        }
    }
"""

QUERY_USERS_LIST_WITH_FILTERS = """
    query GetUsersList($q: String) {
        users(q: $q) {
            edges {
                node {
                    id
                    fullName
                    email
                    isActive
                }
            }
        }
    }
"""


def test_anon_cannot_query_user_by_pk(graphql_client) -> None:
    user = UserFactory()
    response = graphql_client(QUERY, variables={"id": user.pk})
    content = response.json()

    assert content["errors"][0]["message"] == "User is not compatible with the PK strategy"


def test_user_can_query_user_by_relay_id(django_user_client, graphql_user_client) -> None:
    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["isAuthenticated"] is False


def test_user_cant_view_others_private_field(django_user_client, graphql_user_client) -> None:
    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] is None


def test_staff_can_view_others_private_field(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()

    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_superuser_can_view_others_private_field(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_user_with_perm_can_view_others_private_field(
    django_user_client, graphql_user_client
) -> None:
    user = UserFactory()

    perm = Permission.objects.get(
        content_type__app_label=user._meta.app_label, codename="view_user_email"
    )
    django_user_client.user.user_permissions.add(perm)

    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_overcomplex_queries_are_not_executed(graphql_client_with_queries) -> None:
    response, queries = graphql_client_with_queries(MALICIOUS_QUERY)
    content = response.json()

    assert content["errors"][0]["message"] == "Query complexity exceeds the maximum allowed of 3"
    assert queries.count == 0


@override_settings(ENABLE_PUBLIC_ID_LOGIC=False)
def test_anon_can_query_users_list_with_optimized_query(graphql_client_with_queries) -> None:
    UserFactory.create_batch(10)
    ContentType.objects.clear_cache()

    response, queries = graphql_client_with_queries(QUERY_USERS_LIST)
    content = response.json()

    assert queries.count == 1
    assert len(content["data"]["users"]["edges"]) == 10

    # One SELECT users_user LEFT JOIN profiles_profile (page slice; totalCount not selected).


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_can_query_users_list_with_optimized_query_with_public_id(
    graphql_client_with_queries,
) -> None:
    UserFactory.create_batch(10)
    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(QUERY_USERS_LIST)
    content = response.json()

    assert queries.count == 4
    assert len(content["data"]["users"]["edges"]) == 10

    # 1-2. ContentType lookups for users.user and profiles.profile (cold cache), used by the
    #      mapped_public_id subqueries.
    # 3. SELECT users_user with its mapped_public_id subquery (page slice).
    # 4. SELECT profiles_profile with its mapped_public_id subquery for the page's profiles.


def test_anon_can_query_users_list_with_filter_by_email(graphql_client_with_queries) -> None:
    UserFactory.create_batch(2)
    UserFactory(email="test@test.com")
    response, queries = graphql_client_with_queries(
        QUERY_USERS_LIST_WITH_FILTERS, variables={"q": "test@test.com"}
    )
    content = response.json()

    assert len(content["data"]["users"]["edges"]) == 1


def test_anon_can_query_users_list_with_filter_by_profile_name(graphql_client_with_queries) -> None:
    UserFactory.create_batch(2)
    user_1 = UserFactory()
    user_1.profile.name = "test"
    user_1.profile.save()
    user_2 = UserFactory()
    user_2.profile.name = "testing"
    user_2.profile.save()
    response, queries = graphql_client_with_queries(
        QUERY_USERS_LIST_WITH_FILTERS, variables={"q": "test"}
    )
    content = response.json()

    assert len(content["data"]["users"]["edges"]) == 2
