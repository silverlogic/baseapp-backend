import pytest
from constance.test import override_config
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

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


def test_anon_cannot_query_user_by_pk(graphql_client):
    user = UserFactory()
    response = graphql_client(QUERY, variables={"id": user.pk})
    content = response.json()

    assert content["errors"][0]["message"] == "User is not compatible with the PK strategy"


def test_user_can_query_user_by_relay_id(django_user_client, graphql_user_client):
    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["isAuthenticated"] is False


def test_user_cant_view_others_private_field(django_user_client, graphql_user_client):
    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] is None


def test_staff_can_view_others_private_field(django_user_client, graphql_user_client):
    django_user_client.user.is_staff = True
    django_user_client.user.save()

    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_superuser_can_view_others_private_field(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_user_with_perm_can_view_others_private_field(django_user_client, graphql_user_client):
    user = UserFactory()

    perm = Permission.objects.get(
        content_type__app_label=user._meta.app_label, codename="view_user_email"
    )
    django_user_client.user.user_permissions.add(perm)

    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_overcomplex_queries_are_not_executed(graphql_client_with_queries):
    response, queries = graphql_client_with_queries(MALICIOUS_QUERY)
    content = response.json()

    assert content["errors"][0]["message"] == "Query complexity exceeds the maximum allowed of 3"
    assert queries.count == 0


@override_config(ENABLE_PUBLIC_ID_LOGIC=False)
def test_anon_can_query_users_list_with_optimized_query(graphql_client_with_queries):
    UserFactory.create_batch(10)
    response, queries = graphql_client_with_queries(QUERY_USERS_LIST)
    content = response.json()

    assert queries.count == 4
    assert len(content["data"]["users"]["edges"]) == 10

    # With optimizer queries are expected to be 4 and retrieving just the queried fields.
    # The first is a cold-cache ContentType lookup fired by AbstractUserObjectType.pre_optimization_hook
    # (ReactableMetadataService.annotate_queryset embeds the User ct_id in inline Subqueries).
    # SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = users AND "django_content_type"."model" = user) LIMIT 21
    # SELECT "users_user"."id", "users_user"."profile_id", "users_user"."first_name", "users_user"."last_name", ("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AS "password_expiry_date", (("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AT TIME ZONE UTC)::date <= 2025-02-28 AS "is_password_expired", "profiles_profile"."id", "profiles_profile"."name" FROM "users_user" LEFT OUTER JOIN "profiles_profile" ON ("users_user"."profile_id" = "profiles_profile"."id") WHERE "users_user"."is_active"
    # SELECT COUNT(*) AS "__count" FROM "users_user" WHERE "users_user"."is_active"
    # SELECT "users_user"."id", "users_user"."profile_id", "users_user"."first_name", "users_user"."last_name", ("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AS "password_expiry_date", (("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AT TIME ZONE UTC)::date <= 2025-02-28 AS "is_password_expired", "profiles_profile"."id", "profiles_profile"."name" FROM "users_user" LEFT OUTER JOIN "profiles_profile" ON ("users_user"."profile_id" = "profiles_profile"."id") WHERE "users_user"."is_active" LIMIT 10


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_can_query_users_list_with_optimized_query_with_public_id(graphql_client_with_queries):
    UserFactory.create_batch(10)
    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(QUERY_USERS_LIST)
    content = response.json()

    assert queries.count == 7
    assert len(content["data"]["users"]["edges"]) == 10

    # With optimizer queries are expected to be 7:
    # 1. ContentType lookup for users.user (cold-cache; cached after first request in production)
    # 2. ContentType lookup for profiles.profile (cold-cache; same caching as above)
    # 3. SELECT users_user with _ratable_* Subqueries inlined by
    #    AbstractUserObjectType.pre_optimization_hook (RatableMetadataService.annotate_queryset)
    # 4. SELECT profiles_profile with _commentable_*, _followable_*, mapped_public_id Subqueries
    #    inlined by ProfileObjectType.pre_optimization_hook
    # 5. SELECT COUNT(*) for pagination
    # 6. Same as #3 with LIMIT 10 for the returned page slice
    # 7. Same as #4 for the page's profiles
