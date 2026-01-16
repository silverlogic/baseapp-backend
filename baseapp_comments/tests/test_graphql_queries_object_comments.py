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
                                pageInfo {
                                    hasNextPage
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
                    pageInfo {
                        hasNextPage
                        hasPreviousPage
                        startCursor
                        endCursor
                    }
                }
            }
        }
    }
"""


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_see_comments_and_replies(django_user_client, graphql_client_with_queries):
    target = CommentFactory()
    user = django_user_client.user
    replying_user = UserFactory()
    comment = CommentFactory(target=target, user=user)
    CommentFactory.create_batch(target=target, in_reply_to=comment, size=2, user=replying_user)

    response, queries = graphql_client_with_queries(
        VIEW_ALL_QUERY, variables={"id": target.relay_id}
    )
    content = response.json()

    assert content["data"]["node"]["commentsCount"]["main"] == 1
    assert content["data"]["node"]["commentsCount"]["replies"] == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["commentsCount"]["main"] == 2
    assert len(content["data"]["node"]["comments"]["edges"][0]["node"]["comments"]["edges"]) == 2

    assert queries.count == 10

    ### Optimized queries.
    # 1) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "baseapp_core_documentid" INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "baseapp_core_documentid"."public_id" = 97c2483b-2625-448f-ba16-2e58b92a76c3 LIMIT 21',
    # 2) 'SELECT "comments_comment"."id", "comments_comment"."comments_count", "comments_comment"."is_comments_enabled", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total" FROM "comments_comment" WHERE "comments_comment"."id" = 28966 ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 3) 'SELECT "col1", "col2", "col3", "col4", "col5", "col6", "replies_count_total", "reactions_count_total", "mapped_public_id" FROM ( SELECT * FROM ( SELECT "comments_comment"."id" AS "col1", "comments_comment"."comments_count" AS "col2", "comments_comment"."is_comments_enabled" AS "col3", "comments_comment"."target_object_id" AS "col4", "comments_comment"."in_reply_to_id" AS "col5", "comments_comment"."status" AS "col6", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 720 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4" FROM "comments_comment" WHERE "comments_comment"."in_reply_to_id" IN (28966) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC ) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC',
    #
    ### resolve_comments queries:
    # 4) 'SELECT "comments_comment"."id", "comments_comment"."is_comments_enabled", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total" FROM "comments_comment" WHERE (NOT ("comments_comment"."status" = 0) AND "comments_comment"."in_reply_to_id" IS NULL AND "comments_comment"."target_content_type_id" = 720 AND "comments_comment"."target_object_id" = 28966) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 5) 'SELECT "comments_comment"."id", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 720 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id" FROM "comments_comment" WHERE "comments_comment"."in_reply_to_id" IN (28967) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 6) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 715 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (1051)',
    # 7) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id" FROM "baseapp_core_documentid" WHERE ("baseapp_core_documentid"."content_type_id" = 720 AND "baseapp_core_documentid"."object_id" = 28967) LIMIT 21',
    # 8) 'SELECT "comments_comment"."id", "comments_comment"."comments_count" FROM "comments_comment" WHERE "comments_comment"."id" = 28967 LIMIT 21',
    # 9) 'SELECT "comments_comment"."id", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 720 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id" FROM "comments_comment" WHERE ("comments_comment"."in_reply_to_id" = 28967 AND "comments_comment"."status" = 1) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 10) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 715 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (1051)'


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_see_comments_and_replies_with_pagination(
    django_user_client, graphql_client_with_queries
):
    target = CommentFactory()
    user = django_user_client.user
    replying_user = UserFactory()
    comment = CommentFactory(target=target, user=user)
    CommentFactory.create_batch(target=target, in_reply_to=comment, size=110, user=replying_user)

    response, queries = graphql_client_with_queries(
        VIEW_ALL_QUERY, variables={"id": target.relay_id}
    )
    content = response.json()

    assert content["data"]["node"]["commentsCount"]["main"] == 1
    assert content["data"]["node"]["commentsCount"]["replies"] == 110
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["commentsCount"]["main"] == 110
    assert len(content["data"]["node"]["comments"]["edges"][0]["node"]["comments"]["edges"]) == 100
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["comments"]["pageInfo"][
        "hasNextPage"
    ]

    assert queries.count == 10


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
    assert queries.count == 3

    ### Queries Optimized
    # 1) 'SELECT "comments_comment"."id", "comments_comment"."comments_count", "comments_comment"."is_comments_enabled", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total" FROM "comments_comment" WHERE "comments_comment"."id" = 26712 ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 2) 'SELECT "col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "replies_count_total", "reactions_count_total", "_optimizer_count", "col9", "col10", "col11", "col12" FROM ( SELECT * FROM ( SELECT "comments_comment"."id" AS "col1", "comments_comment"."is_comments_enabled" AS "col2", "comments_comment"."user_id" AS "col3", "comments_comment"."profile_id" AS "col4", "comments_comment"."body" AS "col5", "comments_comment"."target_object_id" AS "col6", "comments_comment"."in_reply_to_id" AS "col7", "comments_comment"."status" AS "col8", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT COUNT(*) FROM (SELECT U0."id", U0."is_comments_enabled", U0."user_id", U0."profile_id", U0."body", U0."target_object_id", U0."in_reply_to_id", U0."status", (U0."comments_count" -> total) AS "replies_count_total", (U0."reactions_count" -> total) AS "reactions_count_total", "users_user"."id", "users_user"."first_name", "profiles_profile"."id", "profiles_profile"."name" FROM "comments_comment" U0 LEFT OUTER JOIN "users_user" ON (U0."user_id" = "users_user"."id") LEFT OUTER JOIN "profiles_profile" ON (U0."profile_id" = "profiles_profile"."id") WHERE U0."in_reply_to_id" = ("comments_comment"."in_reply_to_id") ORDER BY U0."is_pinned" DESC, U0."created" DESC) _count) AS "_optimizer_count", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4", "users_user"."id" AS "col9", "users_user"."first_name" AS "col10", "profiles_profile"."id" AS "col11", "profiles_profile"."name" AS "col12" FROM "comments_comment" LEFT OUTER JOIN "users_user" ON ("comments_comment"."user_id" = "users_user"."id") LEFT OUTER JOIN "profiles_profile" ON ("comments_comment"."profile_id" = "profiles_profile"."id") WHERE "comments_comment"."in_reply_to_id" IN (26712) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC ) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC',
    #
    ### --- Note: It repeated the following queries because the resolve_comments method filters the replies by status = 1.
    # 3) 'SELECT "col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "replies_count_total", "reactions_count_total", "_optimizer_count", "col9", "col10", "col11", "col12" FROM ( SELECT * FROM ( SELECT "comments_comment"."id" AS "col1", "comments_comment"."is_comments_enabled" AS "col2", "comments_comment"."user_id" AS "col3", "comments_comment"."profile_id" AS "col4", "comments_comment"."body" AS "col5", "comments_comment"."target_object_id" AS "col6", "comments_comment"."in_reply_to_id" AS "col7", "comments_comment"."status" AS "col8", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT COUNT(*) FROM (SELECT U0."id", U0."is_comments_enabled", U0."user_id", U0."profile_id", U0."body", U0."target_object_id", U0."in_reply_to_id", U0."status", (U0."comments_count" -> total) AS "replies_count_total", (U0."reactions_count" -> total) AS "reactions_count_total", "users_user"."id", "users_user"."first_name", "profiles_profile"."id", "profiles_profile"."name" FROM "comments_comment" U0 LEFT OUTER JOIN "users_user" ON (U0."user_id" = "users_user"."id") LEFT OUTER JOIN "profiles_profile" ON (U0."profile_id" = "profiles_profile"."id") WHERE U0."in_reply_to_id" = ("comments_comment"."in_reply_to_id") ORDER BY U0."is_pinned" DESC, U0."created" DESC) _count) AS "_optimizer_count", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4", "users_user"."id" AS "col9", "users_user"."first_name" AS "col10", "profiles_profile"."id" AS "col11", "profiles_profile"."name" AS "col12" FROM "comments_comment" LEFT OUTER JOIN "users_user" ON ("comments_comment"."user_id" = "users_user"."id") LEFT OUTER JOIN "profiles_profile" ON ("comments_comment"."profile_id" = "profiles_profile"."id") WHERE ("comments_comment"."in_reply_to_id" = 26712 AND "comments_comment"."status" = 1) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC ) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC'


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
    assert queries.count == 11

    ### Optimized queries.
    # 1) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "baseapp_core_documentid" INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "baseapp_core_documentid"."public_id" = 426019ba-e5de-4d20-bef9-7ec0af7c4f4e LIMIT 21',
    # 2) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = comments AND "django_content_type"."model" = comment) LIMIT 21',
    # 3) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = users AND "django_content_type"."model" = user) LIMIT 21',
    # 4) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = profiles AND "django_content_type"."model" = profile) LIMIT 21',
    # 5) 'SELECT "comments_comment"."id", "comments_comment"."comments_count", "comments_comment"."is_comments_enabled", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total" FROM "comments_comment" WHERE "comments_comment"."id" = 26691 ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 6) 'SELECT "col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "replies_count_total", "reactions_count_total", "mapped_public_id", "_optimizer_count" FROM ( SELECT * FROM ( SELECT "comments_comment"."id" AS "col1", "comments_comment"."is_comments_enabled" AS "col2", "comments_comment"."user_id" AS "col3", "comments_comment"."profile_id" AS "col4", "comments_comment"."body" AS "col5", "comments_comment"."target_object_id" AS "col6", "comments_comment"."in_reply_to_id" AS "col7", "comments_comment"."status" AS "col8", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 26 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id", (SELECT COUNT(*) FROM (SELECT V0."id", V0."is_comments_enabled", V0."user_id", V0."profile_id", V0."body", V0."target_object_id", V0."in_reply_to_id", V0."status", (V0."comments_count" -> total) AS "replies_count_total", (V0."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 26 AND U0."object_id" = (V0."id"))) AS "mapped_public_id" FROM "comments_comment" V0 WHERE V0."in_reply_to_id" = ("comments_comment"."in_reply_to_id") ORDER BY V0."is_pinned" DESC, V0."created" DESC) _count) AS "_optimizer_count", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4" FROM "comments_comment" WHERE "comments_comment"."in_reply_to_id" IN (26691) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC ) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC',
    # 7) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 74 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (552)',
    # 8) 'SELECT "profiles_profile"."id", "profiles_profile"."name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 28 AND U0."object_id" = ("profiles_profile"."id"))) AS "mapped_public_id" FROM "profiles_profile" WHERE "profiles_profile"."id" IN (736)',
    #
    ### --- Note: It repeated the following queries because the resolve_comments method filters the replies by status = 1.
    # 9) 'SELECT "col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "replies_count_total", "reactions_count_total", "mapped_public_id", "_optimizer_count" FROM ( SELECT * FROM ( SELECT "comments_comment"."id" AS "col1", "comments_comment"."is_comments_enabled" AS "col2", "comments_comment"."user_id" AS "col3", "comments_comment"."profile_id" AS "col4", "comments_comment"."body" AS "col5", "comments_comment"."target_object_id" AS "col6", "comments_comment"."in_reply_to_id" AS "col7", "comments_comment"."status" AS "col8", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 26 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id", (SELECT COUNT(*) FROM (SELECT V0."id", V0."is_comments_enabled", V0."user_id", V0."profile_id", V0."body", V0."target_object_id", V0."in_reply_to_id", V0."status", (V0."comments_count" -> total) AS "replies_count_total", (V0."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 26 AND U0."object_id" = (V0."id"))) AS "mapped_public_id" FROM "comments_comment" V0 WHERE V0."in_reply_to_id" = ("comments_comment"."in_reply_to_id") ORDER BY V0."is_pinned" DESC, V0."created" DESC) _count) AS "_optimizer_count", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4" FROM "comments_comment" WHERE ("comments_comment"."in_reply_to_id" = 26691 AND "comments_comment"."status" = 1) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC ) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC',
    # 10) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 74 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (552)',
    # 11) 'SELECT "profiles_profile"."id", "profiles_profile"."name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 28 AND U0."object_id" = ("profiles_profile"."id"))) AS "mapped_public_id" FROM "profiles_profile" WHERE "profiles_profile"."id" IN (736)'


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_comments_query_is_partially_optimized_with_public_id_and_pagination(
    django_user_client, graphql_client_with_queries
):
    first_comment = CommentFactory()
    target = CommentFactory(
        user=django_user_client.user, body="test body", in_reply_to=first_comment
    )
    replying_user = UserFactory()
    replying_profile = ProfileFactory(owner=replying_user)
    CommentFactory.create_batch(
        target=target, size=102, user=replying_user, profile=replying_profile, in_reply_to=target
    )

    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(
        SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION, variables={"id": target.relay_id}
    )

    content = response.json()

    assert content["data"]["node"]["commentsCount"]["replies"] == 102
    assert (
        len(content["data"]["node"]["comments"]["edges"]) == 100
    )  # Because the max_limit is 100 by default
    assert content["data"]["node"]["comments"]["pageInfo"]["hasNextPage"]

    assert queries.count == 11


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
    assert queries.count == 8

    ### Optimized queries. About the comments it's only 4 queries.
    # 1) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "baseapp_core_documentid" INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "baseapp_core_documentid"."public_id" = 1e044df1-9a3d-4a26-b056-01f9e1d9dfb5 LIMIT 21',
    # 2) 'SELECT "baseapp_pages_page"."id", "baseapp_pages_page"."created", "baseapp_pages_page"."modified", "baseapp_pages_page"."comments_count", "baseapp_pages_page"."is_comments_enabled", "baseapp_pages_page"."user_id", "baseapp_pages_page"."title_en", "baseapp_pages_page"."title_es", "baseapp_pages_page"."title_pt", "baseapp_pages_page"."body_en", "baseapp_pages_page"."body_es", "baseapp_pages_page"."body_pt", "baseapp_pages_page"."status" FROM "baseapp_pages_page" WHERE "baseapp_pages_page"."id" = 3',
    # 3) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = comments AND "django_content_type"."model" = comment) LIMIT 21',
    # 4) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = users AND "django_content_type"."model" = user) LIMIT 21',
    # 5) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = profiles AND "django_content_type"."model" = profile) LIMIT 21',
    # 6) 'SELECT "comments_comment"."id", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."body", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 26 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id" FROM "comments_comment" WHERE (NOT ("comments_comment"."status" = 0) AND "comments_comment"."in_reply_to_id" IS NULL AND "comments_comment"."target_content_type_id" = 27 AND "comments_comment"."target_object_id" = 3) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 7) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 74 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (567)',
    # 8) 'SELECT "profiles_profile"."id", "profiles_profile"."name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 28 AND U0."object_id" = ("profiles_profile"."id"))) AS "mapped_public_id" FROM "profiles_profile" WHERE "profiles_profile"."id" IN (757)'
