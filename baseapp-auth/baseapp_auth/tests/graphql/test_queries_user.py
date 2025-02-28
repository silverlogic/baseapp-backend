import pytest
from baseapp_core.tests.factories import UserFactory
from django.contrib.auth.models import Permission

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


def test_anon_can_query_user_by_pk(graphql_client):
    user = UserFactory()
    response = graphql_client(QUERY, variables={"id": user.pk})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["pk"] == user.pk
    assert content["data"]["user"]["isAuthenticated"] is False
    assert content["data"]["user"]["email"] is None


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


def test_anon_can_query_users_list_with_only_queried_fields(graphql_client_with_queries):
    users = UserFactory.create_batch(10)
    response, queries = graphql_client_with_queries(QUERY_USERS_LIST)
    content = response.json()

    import pdb; pdb.set_trace()

    assert content["data"]["users"]["edges"][0]["node"]["id"] == str(users[0].relay_id)
    assert content["data"]["users"]["edges"][0]["node"]["firstName"] == users[0].first_name
    assert content["data"]["users"]["edges"][0]["node"]["lastName"] == users[0].last_name
    assert content["data"]["users"]["edges"][1]["node"]["id"] == str(users[1].relay_id)
    assert content["data"]["users"]["edges"][1]["node"]["firstName"] == users[1].first_name
    assert content["data"]["users"]["edges"][1]["node"]["lastName"] == users[1].last_name

    # Validate that the SQL queries include the necessary fields for internal logic
    required_sql_fields = {"id", "first_name", "last_name", "password_changed_date"}
    for query in queries:
        if "SELECT" and not "COUNT" in query:
            # Extract the fields being selected
            select_clause = query.split("SELECT")[1].split("FROM")[0].strip()
            selected_fields = {field.strip().split(" AS ")[0].strip('"') for field in select_clause.split(",")}

            # Ensure that the necessary fields are selected in the SQL query
            assert required_sql_fields.issubset(selected_fields), f"Missing required fields in SQL query: {required_sql_fields - selected_fields}"

    # With optimize queries are expected to be 3 and retrieving just the queried fields:
    #SELECT "users_user"."id", "users_user"."profile_id", "users_user"."first_name", "users_user"."last_name", ("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AS "password_expiry_date", (("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AT TIME ZONE UTC)::date <= 2025-02-28 AS "is_password_expired", "profiles_profile"."id", "profiles_profile"."name" FROM "users_user" LEFT OUTER JOIN "profiles_profile" ON ("users_user"."profile_id" = "profiles_profile"."id") WHERE "users_user"."is_active"
    #SELECT COUNT(*) AS "__count" FROM "users_user" WHERE "users_user"."is_active"
    #SELECT "users_user"."id", "users_user"."profile_id", "users_user"."first_name", "users_user"."last_name", ("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AS "password_expiry_date", (("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AT TIME ZONE UTC)::date <= 2025-02-28 AS "is_password_expired", "profiles_profile"."id", "profiles_profile"."name" FROM "users_user" LEFT OUTER JOIN "profiles_profile" ON ("users_user"."profile_id" = "profiles_profile"."id") WHERE "users_user"."is_active" LIMIT 10

    # Without optimize queries are expected to be 12 (one for each profile) and with all the model attributes:
    # SELECT COUNT(*) AS "__count" FROM "users_user" WHERE "users_user"."is_active"
    # SELECT "users_user"."id", "users_user"."password", "users_user"."last_login", "users_user"."is_superuser", "users_user"."profile_id", "users_user"."email", "users_user"."is_email_verified", "users_user"."date_joined", "users_user"."password_changed_date", "users_user"."new_email", "users_user"."is_new_email_confirmed", "users_user"."first_name", "users_user"."last_name", "users_user"."phone_number", "users_user"."is_active", "users_user"."is_staff", "users_user"."preferred_language", ("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AS "password_expiry_date", (("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AT TIME ZONE UTC)::date <= 2025-02-28 AS "is_password_expired" FROM "users_user" WHERE "users_user"."is_active" LIMIT 10
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 1 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 2 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 3 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 4 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 5 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 6 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 7 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 8 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 9 LIMIT 21
    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" = 10 LIMIT 21