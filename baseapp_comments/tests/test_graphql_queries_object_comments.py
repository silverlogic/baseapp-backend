import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import PageFactory
from baseapp_profiles.tests.factories import ProfileFactory
from baseapp_reactions.tests.factories import ReactionFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

VIEW_ALL_QUERY = """
    query GetObject($id: ID!, $orderBy: String, $q: String) {
        node(id: $id) {
            ... on CommentsInterface {
                commentsCount {
                    main
                    replies
                }
                comments(orderBy: $orderBy, q: $q) {
                    edges {
                        node {
                            id
                            pk
                            commentsCount {
                                main
                                replies
                            }
                            comments {
                                edges {
                                    node {
                                        id
                                        pk
                                        user {
                                            id
                                            firstName
                                        }
                                        profile {
                                            id
                                            name
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


SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION = """
    query GetObject($id: ID!, $orderBy: String, $q: String) {
        node(id: $id) {
            ... on CommentsInterface {
                commentsCount {
                    replies
                }
                comments(orderBy: $orderBy, q: $q) {
                    edges {
                        node {
                            body
                            id
                            pk
                            user {
                                id
                                firstName
                            }
                            profile {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
    }
"""


def test_anon_see_comments_and_replies(django_user_client, graphql_client):
    target = CommentFactory()
    user = django_user_client.user
    replying_user = UserFactory()
    comment = CommentFactory(target=target, user=user)
    CommentFactory.create_batch(target=target, in_reply_to=comment, size=2, user=replying_user)

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id})
    content = response.json()

    assert content["data"]["node"]["commentsCount"]["main"] == 1
    assert content["data"]["node"]["commentsCount"]["replies"] == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["commentsCount"]["main"] == 2
    assert len(content["data"]["node"]["comments"]["edges"][0]["node"]["comments"]["edges"]) == 2


def test_anon_cant_see_comments_when_disabled(graphql_client):
    target = CommentFactory(is_comments_enabled=False)
    CommentFactory(target=target)

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id})
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 0


def test_search(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, body="the s1lv3r logic")

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id, "q": "s1lv3r"})
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 1
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id


def test_order_by_pinned_first(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, is_pinned=True)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "-is_pinned"}
    )
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id


def test_order_by_pinned_last(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, is_pinned=True)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "is_pinned"}
    )
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][-1]["node"]["id"] == comment.relay_id


def test_order_by_reactions_total_desc(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target)
    ReactionFactory(target=comment)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "-reactions_count_total"}
    )
    content = response.json()
    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id


def test_order_by_reactions_total_asc(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target)
    ReactionFactory(target=comment)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "reactions_count_total"}
    )
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][-1]["node"]["id"] == comment.relay_id


def test_order_by_replies_total_desc(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target)
    CommentFactory(target=target, in_reply_to=comment)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "-replies_count_total"}
    )
    content = response.json()
    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id


def test_order_by_replies_total_asc(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, is_pinned=True)
    CommentFactory(target=target, in_reply_to=comment)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "replies_count_total"}
    )
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][-1]["node"]["id"] == comment.relay_id


@override_settings(BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS=False)
def test_anon_cant_see_comments(graphql_client):
    target = CommentFactory()
    CommentFactory(target=target)

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id})
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 0


@override_config(ENABLE_PUBLIC_ID_LOGIC=False)
def test_comments_query_is_partially_optimized(django_user_client, graphql_client_with_queries):
    first_comment = CommentFactory()
    target = CommentFactory(
        user=django_user_client.user, body="test body", in_reply_to=first_comment
    )
    replying_user = UserFactory()
    replying_profile = ProfileFactory(owner=replying_user)
    CommentFactory.create_batch(
        target=target, size=5, user=replying_user, profile=replying_profile, in_reply_to=target
    )

    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(
        SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION, variables={"id": target.relay_id}
    )

    content = response.json()

    assert content["data"]["node"]["commentsCount"]["replies"] == 5
    assert queries.count == 4

    ### Queries Optimized ###

    # 1) SELECT "comments_comment"."id", "comments_comment"."comments_count", "comments_comment"."is_comments_enabled", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status" FROM "comments_comment" WHERE "comments_comment"."id" = 978 ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC;
    # 2) SELECT "col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "col9", "col10", "col11", "col12" FROM (SELECT * FROM (SELECT "comments_comment"."id" AS "col1", "comments_comment"."is_comments_enabled" AS "col2", "comments_comment"."user_id" AS "col3", "comments_comment"."profile_id" AS "col4", "comments_comment"."body" AS "col5", "comments_comment"."target_object_id" AS "col6", "comments_comment"."in_reply_to_id" AS "col7", "comments_comment"."status" AS "col8", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4", "users_user"."id" AS "col9", "users_user"."first_name" AS "col10", "profiles_profile"."id" AS "col11", "profiles_profile"."name" AS "col12" FROM "comments_comment" LEFT OUTER JOIN "users_user" ON ("comments_comment"."user_id" = "users_user"."id") LEFT OUTER JOIN "profiles_profile" ON ("comments_comment"."profile_id" = "profiles_profile"."id") WHERE "comments_comment"."in_reply_to_id" IN (978) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0"))) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC;

    ### --- Note: It repeated the following queries because the resolve_comments method filters the replies by status = 1.
    # 3) SELECT COUNT(*) FROM (SELECT "col1" FROM (SELECT * FROM (SELECT "comments_comment"."id" AS "col1", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2" FROM "comments_comment" WHERE ("comments_comment"."in_reply_to_id" = 978 AND "comments_comment"."status" = 1)) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0"))) "qualify_mask") subquery;
    # 4) SELECT "col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "col9", "col10", "col11", "col12" FROM (SELECT * FROM (SELECT "comments_comment"."id" AS "col1", "comments_comment"."is_comments_enabled" AS "col2", "comments_comment"."user_id" AS "col3", "comments_comment"."profile_id" AS "col4", "comments_comment"."body" AS "col5", "comments_comment"."target_object_id" AS "col6", "comments_comment"."in_reply_to_id" AS "col7", "comments_comment"."status" AS "col8", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4", "users_user"."id" AS "col9", "users_user"."first_name" AS "col10", "profiles_profile"."id" AS "col11", "profiles_profile"."name" AS "col12" FROM "comments_comment" LEFT OUTER JOIN "users_user" ON ("comments_comment"."user_id" = "users_user"."id") LEFT OUTER JOIN "profiles_profile" ON ("comments_comment"."profile_id" = "profiles_profile"."id") WHERE ("comments_comment"."in_reply_to_id" = 978 AND "comments_comment"."status" = 1) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0"))) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC LIMIT 5;


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_comments_query_is_partially_optimized_with_public_id(
    django_user_client, graphql_client_with_queries
):
    first_comment = CommentFactory()
    target = CommentFactory(
        user=django_user_client.user, body="test body", in_reply_to=first_comment
    )
    replying_user = UserFactory()
    replying_profile = ProfileFactory(owner=replying_user)
    CommentFactory.create_batch(
        target=target, size=5, user=replying_user, profile=replying_profile, in_reply_to=target
    )

    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(
        SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION, variables={"id": target.relay_id}
    )

    content = response.json()

    assert content["data"]["node"]["commentsCount"]["replies"] == 5
    assert queries.count == 12

    # Optimized queries.

    # 1) SELECT ... FROM baseapp_core_publicidmapping INNER JOIN django_content_type ON (...) WHERE baseapp_core_publicidmapping.public_id = 5e5e17d2-07d8-4820-9a34-e13639c10767 LIMIT 21
    # 2) SELECT id, app_label, model FROM django_content_type WHERE (app_label = comments AND model = comment) LIMIT 21
    # 3) SELECT id, app_label, model FROM django_content_type WHERE (app_label = users AND model = user) LIMIT 21
    # 4) SELECT id, app_label, model FROM django_content_type WHERE (app_label = profiles AND model = profile) LIMIT 21
    # 5) SELECT id, comments_count, is_comments_enabled, target_object_id, in_reply_to_id, status FROM comments_comment WHERE id = 964 ORDER BY is_pinned DESC, created DESC
    # 6) SELECT col1, col2, col3, col4, col5, col6, col7, col8, mapped_public_id FROM (...) WHERE (qual1 >= qual2 AND qual1 < qual0) ORDER BY qual3 DESC, qual4 DESC
    # 7) SELECT id, first_name, password_changed_date + interval AS password_expiry_date, ..., mapped_public_id FROM users_user WHERE id IN (669)
    # 8) SELECT id, name, (SELECT public_id FROM publicidmapping ...) AS mapped_public_id FROM profiles_profile WHERE id IN (763)
    # 9) SELECT COUNT(*) FROM (...) WHERE (qual1 >= qual2 AND qual1 < qual0)

    ### --- Note: It repeated the following queries because the resolve_comments method filters the replies by status = 1.

    # 10) SELECT col1, col2, col3, col4, col5, col6, col7, col8, mapped_public_id FROM (...) WHERE (in_reply_to_id = 964 AND status = 1) ORDER BY is_pinned DESC, created DESC LIMIT 5
    # 11) SELECT id, first_name, password_changed_date + interval AS password_expiry_date, ..., mapped_public_id FROM users_user WHERE id IN (669)
    # 12) SELECT id, name, (SELECT public_id FROM publicidmapping ...) AS mapped_public_id FROM profiles_profile WHERE id IN (763)


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_comments_query_from_foreigh_target_is_partially_optimized_with_public_id(
    django_user_client,
    graphql_client_with_queries,
):
    target = PageFactory(user=django_user_client.user)

    user = UserFactory()
    profile = ProfileFactory(owner=user)

    CommentFactory.create_batch(target=target, size=5, user=user, profile=profile)

    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(
        SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION, variables={"id": target.relay_id}
    )

    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 5
    assert queries.count == 9

    # Optimized queries. About the comments it's only 4 queries.

    # 1) SELECT "baseapp_core_publicidmapping"."created", "baseapp_core_publicidmapping"."modified", "baseapp_core_publicidmapping"."public_id", "baseapp_core_publicidmapping"."content_type_id", "baseapp_core_publicidmapping"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "baseapp_core_publicidmapping" INNER JOIN "django_content_type" ON ("baseapp_core_publicidmapping"."content_type_id" = "django_content_type"."id") WHERE "baseapp_core_publicidmapping"."public_id" = 4e79d2a3-4195-4d12-b202-a074ade2f052 LIMIT 21;
    # 2) SELECT "baseapp_pages_page"."id", "baseapp_pages_page"."created", "baseapp_pages_page"."modified", "baseapp_pages_page"."comments_count", "baseapp_pages_page"."is_comments_enabled", "baseapp_pages_page"."user_id", "baseapp_pages_page"."title_en", "baseapp_pages_page"."title_es", "baseapp_pages_page"."title_pt", "baseapp_pages_page"."body_en", "baseapp_pages_page"."body_es", "baseapp_pages_page"."body_pt", "baseapp_pages_page"."status" FROM "baseapp_pages_page" WHERE "baseapp_pages_page"."id" = 38;
    # 3) SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = comments AND "django_content_type"."model" = comment) LIMIT 21;
    # 4) SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = users AND "django_content_type"."model" = user) LIMIT 21;
    # 5) SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = profiles AND "django_content_type"."model" = profile) LIMIT 21;
    # 6) SELECT COUNT(*) AS "__count" FROM "comments_comment" WHERE (NOT ("comments_comment"."status" = 0) AND "comments_comment"."in_reply_to_id" IS NULL AND "comments_comment"."target_content_type_id" = 26 AND "comments_comment"."target_object_id" = 38);
    # 7) SELECT "comments_comment"."id", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."body", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", (SELECT U0."public_id" FROM "baseapp_core_publicidmapping" U0 WHERE (U0."content_type_id" = 25 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id" FROM "comments_comment" WHERE (NOT ("comments_comment"."status" = 0) AND "comments_comment"."in_reply_to_id" IS NULL AND "comments_comment"."target_content_type_id" = 26 AND "comments_comment"."target_object_id" = 38) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC LIMIT 5;
    # 8) SELECT "users_user"."id", "users_user"."first_name", ("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AS "password_expiry_date", (("users_user"."password_changed_date" + (730 days, 0:00:00)::interval) AT TIME ZONE UTC)::date <= 2025-09-17 AS "is_password_expired", (SELECT U0."public_id" FROM "baseapp_core_publicidmapping" U0 WHERE (U0."content_type_id" = 86 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (681);
    # 9) SELECT "profiles_profile"."id", "profiles_profile"."name", (SELECT U0."public_id" FROM "baseapp_core_publicidmapping" U0 WHERE (U0."content_type_id" = 27 AND U0."object_id" = ("profiles_profile"."id"))) AS "mapped_public_id" FROM "profiles_profile" WHERE "profiles_profile"."id" IN (780);
