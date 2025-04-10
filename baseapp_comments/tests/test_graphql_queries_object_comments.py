import pytest
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory
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

    response, queries = graphql_client_with_queries(
        SIMPLIFIED_QUERY_FOR_TESTING_OPTIMIZATION, variables={"id": target.relay_id}
    )

    content = response.json()

    assert content["data"]["node"]["commentsCount"]["replies"] == 5
    assert queries.count == 5

    ### Queries with select_related("user", "profile") under comments get_queryset ###

    # SELECT "comments_comment"."id", "comments_comment"."created", "comments_comment"."modified", "comments_comment"."reports_count", "comments_comment"."reactions_count", "comments_comment"."is_reactions_enabled", "comments_comment"."comments_count", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."body", "comments_comment"."language", "comments_comment"."is_edited", "comments_comment"."is_pinned", "comments_comment"."target_content_type_id", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status" FROM "comments_comment" WHERE "comments_comment"."id" = 2 ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC

    # SELECT COUNT(*) AS "__count" FROM "comments_comment" WHERE ("comments_comment"."in_reply_to_id" = 2 AND "comments_comment"."status" = 1)

    # SELECT "comments_comment"."id", "comments_comment"."created", "comments_comment"."modified", "comments_comment"."reports_count", "comments_comment"."reactions_count", "comments_comment"."is_reactions_enabled", "comments_comment"."comments_count", "comments_comment"."is_comments_enabled", "comments_comment"."user_id", "comments_comment"."profile_id", "comments_comment"."body", "comments_comment"."language", "comments_comment"."is_edited", "comments_comment"."is_pinned", "comments_comment"."target_content_type_id", "comments_comment"."target_object_id", "comments_comment"."in_reply_to_id", "comments_comment"."status" FROM "comments_comment" WHERE ("comments_comment"."in_reply_to_id" = 2 AND "comments_comment"."status" = 1) ORDER BY "comments_comment"."is_pinned" DESC, "comments_comment"."created" DESC LIMIT 5

    # SELECT "profiles_profile"."id", "profiles_profile"."created", "profiles_profile"."modified", "profiles_profile"."blockers_count", "profiles_profile"."blocking_count", "profiles_profile"."followers_count", "profiles_profile"."following_count", "profiles_profile"."reports_count", "profiles_profile"."comments_count", "profiles_profile"."is_comments_enabled", "profiles_profile"."name", "profiles_profile"."image", "profiles_profile"."banner_image", "profiles_profile"."biography", "profiles_profile"."target_content_type_id", "profiles_profile"."target_object_id", "profiles_profile"."status", "profiles_profile"."owner_id" FROM "profiles_profile" WHERE "profiles_profile"."id" IN (4)

    # SELECT "users_user"."id", "users_user"."password", "users_user"."last_login", "users_user"."is_superuser", "users_user"."profile_id", "users_user"."email", "users_user"."is_email_verified", "users_user"."date_joined", "users_user"."password_changed_date", "users_user"."new_email", "users_user"."is_new_email_confirmed", "users_user"."first_name", "users_user"."last_name", "users_user"."phone_number", "users_user"."is_active", "users_user"."is_staff", "users_user"."preferred_language" FROM "users_user" WHERE "users_user"."id" IN (3)
