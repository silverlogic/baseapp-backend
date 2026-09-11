import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from baseapp_blocks.tests.factories import BlockFactory
from baseapp_core.plugins import shared_services
from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import PageFactory
from baseapp_profiles.tests.factories import ProfileFactory
from baseapp_reactions.tests.factories import ReactionFactory

from .factories import Comment, CommentFactory

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

PAGINATED_COMMENTS_QUERY = """
    query GetObject($id: ID!, $first: Int, $after: String, $orderBy: String) {
        node(id: $id) {
                id
            ... on CommentsInterface {
                commentsCount {
                    total
                    main
                }
                comments(first: $first, after: $after, orderBy: $orderBy) {
                    edges {
                        node {
                            id
                            pk
                            commentsCount {
                                total
                                main
                                replies
                            }
                            comments(first: 5) {
                                edges {
                                    node {
                                        id
                                        pk
                                    }
                                }
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                            }
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
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
                            commentsCount {
                                main
                                replies
                            }
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
def test_anon_see_comments_and_replies(django_user_client, graphql_client_with_queries) -> None:
    target = CommentFactory()
    user = django_user_client.user
    replying_user = UserFactory()
    comment = CommentFactory(target=target, user=user)
    CommentFactory.create_batch(target=target, in_reply_to=comment, size=2, user=replying_user)
    ContentType.objects.clear_cache()

    response, queries = graphql_client_with_queries(
        VIEW_ALL_QUERY, variables={"id": target.relay_id}
    )
    content = response.json()

    assert content["data"]["node"]["commentsCount"]["main"] == 1
    assert content["data"]["node"]["commentsCount"]["replies"] == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["commentsCount"]["main"] == 2
    assert len(content["data"]["node"]["comments"]["edges"][0]["node"]["comments"]["edges"]) == 2

    assert queries.count == 13

    ### Optimized queries.
    ### Queries 2 and 3 are ContentType lookups; they are usually cached after
    ### an earlier request in production, but we clear the cache here to make the
    ### query count deterministic.
    # 1) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "baseapp_core_documentid" INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "baseapp_core_documentid"."public_id" = e8aa1f94-9fd5-4add-9979-431e014e2625 LIMIT 21',
    # 2) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = users AND "django_content_type"."model" = user) LIMIT 21',
    # 3) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = profiles AND "django_content_type"."model" = profile) LIMIT 21',
    # 4) 'SELECT "comments_comment"."id", "comments_comment"."target_document_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", (SELECT U0."comments_count" AS "comments_count" FROM "comments_commentablemetadata" U0 INNER JOIN "baseapp_core_documentid" U1 ON (U0."target_id" = U1."id") WHERE (U1."content_type_id" = 3277 AND U1."object_id" = ("comments_comment"."id")) LIMIT 1) AS "_commentable_comments_count", (SELECT U0."is_comments_enabled" AS "is_comments_enabled" FROM "comments_commentablemetadata" U0 INNER JOIN "baseapp_core_documentid" U1 ON (U0."target_id" = U1."id") WHERE (U1."content_type_id" = 3277 AND U1."object_id" = ("comments_comment"."id")) LIMIT 1) AS "_commentable_is_comments_enabled", COALESCE((SELECT ((U0."comments_count" ->> total))::integer AS "_reply_total" FROM "comments_commentablemetadata" U0 INNER JOIN "baseapp_core_documentid" U1 ON (U0."target_id" = U1."id") WHERE (U1."content_type_id" = 3277 AND U1."object_id" = ("comments_comment"."id")) LIMIT 1), 0) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "comments_comment"."id" = 477 ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 5) 'SELECT "col1", "col2", "col3", "col4", "_commentable_comments_count", "_commentable_is_comments_enabled", "replies_count_total", "reactions_count_total", "mapped_public_id", "col5", "col6", "col7", "col8", "col9", "col10", "col11", "col12", "col13" FROM ( SELECT * FROM ( SELECT "comments_comment"."id" AS "col1", "comments_comment"."target_document_id" AS "col2", "comments_comment"."in_reply_to_id" AS "col3", "comments_comment"."status" AS "col4", (SELECT U0."comments_count" ... LIMIT 1) AS "_commentable_comments_count", (SELECT U0."is_comments_enabled" ... LIMIT 1) AS "_commentable_is_comments_enabled", COALESCE(...) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" ... ) AS "mapped_public_id", 100 AS "qual0", (ROW_NUMBER() OVER (PARTITION BY "comments_comment"."in_reply_to_id" ORDER BY ...) - 1) AS "qual1", 0 AS "qual2", "comments_comment"."is_pinned" AS "qual3", "comments_comment"."created" AS "qual4", "baseapp_core_documentid".* AS cols, "django_content_type".* AS cols FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "comments_comment"."in_reply_to_id" IN (477) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC ) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC',
    #
    ### resolve_comments queries (top-level connection on the target):
    # 6) 'SELECT COUNT(*) AS "__count" FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE (NOT ("comments_comment"."status" = 0) AND ("comments_comment"."in_reply_to_id" = 477 OR ("comments_comment"."in_reply_to_id" IS NULL AND "django_content_type"."app_label" = comments AND "django_content_type"."model" = comment AND "baseapp_core_documentid"."object_id" = 477)))',
    # 7) 'SELECT "comments_comment"."id", "comments_comment"."target_document_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", <commentable metadata subqueries>, ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", "baseapp_core_documentid".*, "django_content_type".* FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE (NOT ("comments_comment"."status" = 0) AND ("comments_comment"."in_reply_to_id" = 477 OR ("comments_comment"."in_reply_to_id" IS NULL AND "django_content_type"."app_label" = comments AND "django_content_type"."model" = comment AND "baseapp_core_documentid"."object_id" = 477))) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC LIMIT 1',
    # 8) 'SELECT <comment cols + commentable metadata + mapped_public_id + _optimizer_count + window funcs>, "baseapp_core_documentid".*, "django_content_type".* FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "comments_comment"."in_reply_to_id" IN (478) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC) "qualify" WHERE ("qual1" >= ("qual2") AND "qual1" < ("qual0")) ) "qualify_mask" ORDER BY "qual3" DESC, "qual4" DESC',
    # 9) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" AS "public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 3272 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE ("users_user"."id") IN ((1129))',
    #
    ### Nested replies connection on the comment node (status-filtered duplicate):
    # 10) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id" FROM "baseapp_core_documentid" WHERE ("baseapp_core_documentid"."content_type_id" = 3277 AND "baseapp_core_documentid"."object_id" = 478) LIMIT 21',
    # 11) 'SELECT COUNT(*) AS "__count" FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE (NOT ("comments_comment"."status" = 0) AND ("comments_comment"."in_reply_to_id" = 478 OR ("comments_comment"."in_reply_to_id" IS NULL AND "django_content_type"."app_label" = comments AND "django_content_type"."model" = comment AND "baseapp_core_documentid"."object_id" = 478)))',
    # 12) 'SELECT "comments_comment".*, <commentable metadata subqueries>, "baseapp_core_documentid".*, "django_content_type".* FROM "comments_comment" INNER JOIN "baseapp_core_documentid" ON ("comments_comment"."target_document_id" = "baseapp_core_documentid"."id") INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE (NOT ("comments_comment"."status" = 0) AND ("comments_comment"."in_reply_to_id" = 478 OR ("comments_comment"."in_reply_to_id" IS NULL AND "django_content_type"."app_label" = comments AND "django_content_type"."model" = comment AND "baseapp_core_documentid"."object_id" = 478))) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC LIMIT 2',
    # 13) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" AS "public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 3272 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE ("users_user"."id") IN ((1129))'


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_see_comments_and_replies_with_pagination(
    django_user_client, graphql_client_with_queries
) -> None:
    target = CommentFactory()
    user = django_user_client.user
    replying_user = UserFactory()
    comment = CommentFactory(target=target, user=user)
    CommentFactory.create_batch(target=target, in_reply_to=comment, size=110, user=replying_user)
    ContentType.objects.clear_cache()

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

    assert queries.count == 13


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_top_level_comments_pagination_on_page_target(django_user_client, graphql_client) -> None:
    """Reproduces the FE bug: when using first=5 on the top-level comments
    of a Page (matching the FE CommentsList query), hasNextPage must be True
    when there are more than 5 comments."""
    page = PageFactory(user=django_user_client.user)
    user = UserFactory()
    # Create 10 top-level comments — more than the page size of 5
    CommentFactory.create_batch(target=page, size=10, user=user)

    response = graphql_client(
        PAGINATED_COMMENTS_QUERY,
        variables={"id": page.relay_id, "first": 5},
    )
    content = response.json()

    comments_connection = content["data"]["node"]["comments"]
    assert len(comments_connection["edges"]) == 5
    assert comments_connection["pageInfo"]["hasNextPage"] is True


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_top_level_comments_pagination_on_comment_target(
    django_user_client, graphql_client
) -> None:
    """Same bug but with a Comment as target (how baseapp tests are structured)."""
    target = CommentFactory()
    user = UserFactory()
    # Create 10 top-level comments — more than the page size of 5
    CommentFactory.create_batch(target=target, size=10, user=user)

    response = graphql_client(
        PAGINATED_COMMENTS_QUERY,
        variables={"id": target.relay_id, "first": 5},
    )
    content = response.json()

    comments_connection = content["data"]["node"]["comments"]
    assert len(comments_connection["edges"]) == 5
    assert comments_connection["pageInfo"]["hasNextPage"] is True


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_logged_user_replies_to_a_page_comment_has_next_page_true_when_more_than_5_replies(
    django_user_client, graphql_user_client
) -> None:
    page = PageFactory(user=django_user_client.user)
    user = UserFactory()
    comment = CommentFactory(target=page, user=user)
    replying_user = UserFactory()
    # Create 10 replies — more than the page size of 5
    CommentFactory.create_batch(target=page, in_reply_to=comment, size=10, user=replying_user)

    response = graphql_user_client(
        PAGINATED_COMMENTS_QUERY,
        variables={"id": page.relay_id, "first": 5},
    )
    content = response.json()
    page = content["data"]["node"]

    assert page["commentsCount"]["main"] == 1
    assert page["commentsCount"]["total"] == 11

    page_comments = page["comments"]

    page_comment = page_comments["edges"][0]["node"]
    assert page_comment["commentsCount"]["total"] == 10

    comment_replies = page_comment["comments"]
    assert len(comment_replies["edges"]) == 5
    assert comment_replies["pageInfo"]["hasNextPage"] is True


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_get_queryset_skips_filtering_only_when_hint_set(
    django_user_client, graphql_user_client
) -> None:
    """get_queryset() must rely on the explicit _BLOCKED_PROFILES_FILTERED_HINT
    flag — NOT on _result_cache — to decide whether to skip blocked-profile
    filtering.  A queryset whose _result_cache is populated but lacks the hint
    must still apply the .exclude()."""
    from baseapp_blocks.services import _BLOCKED_PROFILES_FILTERED_HINT
    from baseapp_comments.graphql.object_types import BaseCommentObjectType

    page = PageFactory(user=django_user_client.user)
    current_profile = ProfileFactory(owner=django_user_client.user)

    blocked_user = UserFactory()
    blocked_profile = ProfileFactory(owner=blocked_user)
    BlockFactory(actor=current_profile, target=blocked_profile)

    CommentFactory.create_batch(target=page, size=3, user=django_user_client.user)
    CommentFactory.create_batch(target=page, size=2, user=blocked_user, profile=blocked_profile)

    qs = Comment.objects_visible.for_target(page)

    # Build a fake info object with the authenticated user + current_profile
    class FakeRequest:
        def __init__(self, user, profile) -> None:
            self.user = user
            self.user.current_profile = profile

    class FakeInfo:
        def __init__(self, request) -> None:
            self.context = request

    info = FakeInfo(FakeRequest(django_user_client.user, current_profile))

    # --- Case 1: hint IS set → get_queryset skips filtering (returns as-is)
    service = shared_services.get("blocks.lookup")
    qs_with_hint = service.exclude_blocked_from_foreign_queryset(qs, info)
    assert qs_with_hint._hints.get(_BLOCKED_PROFILES_FILTERED_HINT) is True
    # Filtering was already applied by _exclude_blocked_profiles_from_foreign_queryset
    assert qs_with_hint.count() == 3

    result = BaseCommentObjectType.get_queryset(qs_with_hint, info)
    # Should return the same queryset without applying .exclude() again
    assert result.count() == 3

    # --- Case 2: hint NOT set → get_queryset applies filtering
    qs_no_hint = Comment.objects_visible.for_target(page)
    assert _BLOCKED_PROFILES_FILTERED_HINT not in qs_no_hint._hints
    result = BaseCommentObjectType.get_queryset(qs_no_hint, info)
    assert result.count() == 3  # blocked user's comments excluded

    # --- Case 3: _result_cache populated WITHOUT hint → must still filter
    qs_cached = Comment.objects_visible.for_target(page)
    list(qs_cached)  # populates _result_cache
    assert qs_cached._result_cache is not None
    assert _BLOCKED_PROFILES_FILTERED_HINT not in qs_cached._hints
    result = BaseCommentObjectType.get_queryset(qs_cached, info)
    assert result.count() == 3  # blocked user's comments excluded despite cache


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_blocked_profiles_excluded_with_pagination(django_user_client, graphql_user_client) -> None:
    """Blocked/blocking profiles are excluded and pagination still works correctly."""
    page = PageFactory(user=django_user_client.user)
    current_profile = ProfileFactory(owner=django_user_client.user)

    blocked_user = UserFactory()
    blocked_profile = ProfileFactory(owner=blocked_user)
    BlockFactory(actor=current_profile, target=blocked_profile)

    visible_user = UserFactory()
    # 7 visible comments + 3 from blocked profile = 10 total
    visible_comments = CommentFactory.create_batch(target=page, size=7, user=visible_user)
    CommentFactory.create_batch(target=page, size=3, user=blocked_user, profile=blocked_profile)

    response = graphql_user_client(
        PAGINATED_COMMENTS_QUERY,
        variables={"id": page.relay_id, "first": 5},
        headers={"HTTP_CURRENT_PROFILE": current_profile.relay_id},
    )
    content = response.json()

    comments_connection = content["data"]["node"]["comments"]
    visible_pks = {c.pk for c in visible_comments}

    # Only visible comments appear, none from the blocked profile
    for edge in comments_connection["edges"]:
        assert int(edge["node"]["pk"]) in visible_pks

    assert len(comments_connection["edges"]) == 5
    assert comments_connection["pageInfo"]["hasNextPage"] is True
    assert comments_connection["pageInfo"]["endCursor"] is not None


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_top_level_comments_second_page_with_cursor(django_user_client, graphql_client) -> None:
    """Fetching the second page with an `after` cursor returns the remaining comments."""
    page = PageFactory(user=django_user_client.user)
    user = UserFactory()
    CommentFactory.create_batch(target=page, size=8, user=user)

    # Fetch first page
    response = graphql_client(
        PAGINATED_COMMENTS_QUERY,
        variables={"id": page.relay_id, "first": 5},
    )
    first_page = response.json()["data"]["node"]["comments"]
    assert len(first_page["edges"]) == 5
    assert first_page["pageInfo"]["hasNextPage"] is True
    end_cursor = first_page["pageInfo"]["endCursor"]

    # Fetch second page using the cursor
    response = graphql_client(
        PAGINATED_COMMENTS_QUERY,
        variables={"id": page.relay_id, "first": 5, "after": end_cursor},
    )
    second_page = response.json()["data"]["node"]["comments"]
    assert len(second_page["edges"]) == 3
    assert second_page["pageInfo"]["hasNextPage"] is False

    # Ensure no overlap between pages
    first_page_pks = {e["node"]["pk"] for e in first_page["edges"]}
    second_page_pks = {e["node"]["pk"] for e in second_page["edges"]}
    assert first_page_pks.isdisjoint(second_page_pks)


def test_anon_cant_see_comments_when_disabled(graphql_client) -> None:
    target = CommentFactory(is_comments_enabled=False)
    CommentFactory(target=target)

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id})
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 0


def test_search(graphql_client) -> None:
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, body="the s1lv3r logic")

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id, "q": "s1lv3r"})
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 1
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id


def test_order_by_pinned_first(graphql_client) -> None:
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, is_pinned=True)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "-is_pinned"}
    )
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][0]["node"]["id"] == comment.relay_id


def test_order_by_pinned_last(graphql_client) -> None:
    target = CommentFactory()
    CommentFactory(target=target)
    comment = CommentFactory(target=target, is_pinned=True)

    response = graphql_client(
        VIEW_ALL_QUERY, variables={"id": target.relay_id, "orderBy": "is_pinned"}
    )
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 2
    assert content["data"]["node"]["comments"]["edges"][-1]["node"]["id"] == comment.relay_id


def test_order_by_reactions_total_desc(graphql_client) -> None:
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


def test_order_by_reactions_total_asc(graphql_client) -> None:
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


def test_order_by_replies_total_desc(graphql_client) -> None:
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


def test_order_by_replies_total_asc(graphql_client) -> None:
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
def test_anon_cant_see_comments(graphql_client) -> None:
    target = CommentFactory()
    CommentFactory(target=target)

    response = graphql_client(VIEW_ALL_QUERY, variables={"id": target.relay_id})
    content = response.json()

    assert len(content["data"]["node"]["comments"]["edges"]) == 0


@override_config(ENABLE_PUBLIC_ID_LOGIC=False)
def test_comments_query_is_partially_optimized(
    django_user_client, graphql_client_with_queries
) -> None:
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
    assert queries.count == 7

    # With optimizer queries are expected to be 7:
    # 1. ContentType lookup for comments.comment (cold-cache; cached after first request in production)
    # 2. ContentType lookup for users.user (fired by AbstractUserObjectType.pre_optimization_hook
    #    when the optimizer walks the comments.user FK)
    # 3. ContentType lookup for profiles.profile (fired by ProfileObjectType.pre_optimization_hook
    #    when the optimizer walks the comments.profile FK)
    # 4. SELECT root comments_comment by id with _commentable_* and reply-count Subqueries
    #    inlined by CommentableMetadataService.annotate_queryset
    # 5. SELECT replies (CTE-shaped) for commentsCount with _commentable_*, _reactable_*,
    #    replies_count_total, reactions_count_total Subqueries + JOIN users_user, profiles_profile
    # 6. SELECT COUNT(*) for pagination
    # 7. Same as #5 with status = 1 filter — resolve_comments runs a second query because it
    #    filters replies by status; this is the "partially optimized" part the test name refers to


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_comments_query_is_optimized_with_nested_replies(
    django_user_client, graphql_client_with_queries
) -> None:
    first_comment = CommentFactory()
    target = CommentFactory(
        user=django_user_client.user, body="test body", in_reply_to=first_comment
    )
    replying_user = UserFactory()
    replying_profile = ProfileFactory(owner=replying_user)
    top_level_replies = CommentFactory.create_batch(
        target=target, size=5, user=replying_user, profile=replying_profile, in_reply_to=target
    )
    # Nested reply so at least one comment in the list has replies > 0 on commentsCount.
    CommentFactory.create_batch(
        target=target,
        size=5,
        user=replying_user,
        profile=replying_profile,
        in_reply_to=top_level_replies[0],
    )
    CommentFactory.create_batch(
        target=target,
        size=5,
        user=replying_user,
        profile=replying_profile,
        in_reply_to=top_level_replies[1],
    )

    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(
        SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION, variables={"id": target.relay_id}
    )

    content = response.json()

    assert content["data"]["node"]["commentsCount"]["replies"] == 15
    comment_nodes = [e["node"] for e in content["data"]["node"]["comments"]["edges"]]
    assert any(n["commentsCount"]["main"] >= 1 for n in comment_nodes)
    # Root + nested comments connections (incl. status-filtered duplicate) + metadata subqueries;
    # stays flat (no per-row CommentableMetadata fetch) thanks to annotate_queryset on both optimizers.
    assert queries.count == 12


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_comments_query_is_partially_optimized_with_public_id(
    django_user_client, graphql_client_with_queries
) -> None:
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
) -> None:
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

    assert queries.count == 12


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_comments_query_from_foreigh_target_is_partially_optimized_with_public_id(
    django_user_client,
    graphql_client_with_queries,
) -> None:
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

    ### Optimized queries. About the comments it's only 4 queries.
    # 1) 'SELECT "baseapp_core_documentid"."id", "baseapp_core_documentid"."created", "baseapp_core_documentid"."modified", "baseapp_core_documentid"."public_id", "baseapp_core_documentid"."content_type_id", "baseapp_core_documentid"."object_id", "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "baseapp_core_documentid" INNER JOIN "django_content_type" ON ("baseapp_core_documentid"."content_type_id" = "django_content_type"."id") WHERE "baseapp_core_documentid"."public_id" = 1e044df1-9a3d-4a26-b056-01f9e1d9dfb5 LIMIT 21',
    # 2) 'SELECT "baseapp_pages_page"."id", "baseapp_pages_page"."created", "baseapp_pages_page"."modified", "baseapp_pages_page"."comments_count", "baseapp_pages_page"."is_comments_enabled", "baseapp_pages_page"."user_id", "baseapp_pages_page"."title_en", "baseapp_pages_page"."title_es", "baseapp_pages_page"."title_pt", "baseapp_pages_page"."body_en", "baseapp_pages_page"."body_es", "baseapp_pages_page"."body_pt", "baseapp_pages_page"."status" FROM "baseapp_pages_page" WHERE "baseapp_pages_page"."id" = 3',
    # 3) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = comments AND "django_content_type"."model" = comment) LIMIT 21',
    # 4) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = users AND "django_content_type"."model" = user) LIMIT 21',
    # 5) 'SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model" FROM "django_content_type" WHERE ("django_content_type"."app_label" = profiles AND "django_content_type"."model" = profile) LIMIT 21',
    # 6) 'SELECT "comments_comment"."id", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."body", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status", ("comments_comment"."comments_count" -> total) AS "replies_count_total", ("comments_comment"."reactions_count" -> total) AS "reactions_count_total", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 26 AND U0."object_id" = ("comments_comment"."id"))) AS "mapped_public_id" FROM "comments_comment" WHERE (NOT ("comments_comment"."status" = 0) AND "comments_comment"."in_reply_to_id" IS NULL AND "comments_comment"."target_content_type_id" = 27 AND "comments_comment"."target_object_id" = 3) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC',
    # 7) 'SELECT "users_user"."id", "users_user"."first_name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 74 AND U0."object_id" = ("users_user"."id"))) AS "mapped_public_id" FROM "users_user" WHERE "users_user"."id" IN (567)',
    # 8) 'SELECT "profiles_profile"."id", "profiles_profile"."name", (SELECT U0."public_id" FROM "baseapp_core_documentid" U0 WHERE (U0."content_type_id" = 28 AND U0."object_id" = ("profiles_profile"."id"))) AS "mapped_public_id" FROM "profiles_profile" WHERE "profiles_profile"."id" IN (757)'
