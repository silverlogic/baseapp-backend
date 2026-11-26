"""GraphQL tests for `MentionsInterface` resolvers.

Two concerns:

1. The resolvers (`mentions`, `mentions_count`, `is_mentioning_profile`)
   correctly read the through-table.
2. The `mentions` connection scales — paginating N parents that each expose
   `mentions` does not issue an unbounded number of queries. This pins the
   cost so a future regression (e.g. dropping `select_related("profile")`
   from the resolver) trips the test.
"""

import pytest

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.testing import assert_max_queries
from baseapp_mentions.tests.helpers import seed_mentions
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


COMMENTS_LIST_WITH_MENTIONS = """
    query CommentsListWithMentions($targetId: ID!) {
        node(id: $targetId) {
            ... on CommentsInterface {
                comments(first: 10) {
                    edges {
                        node {
                            id
                            mentions(first: 10) {
                                edges {
                                    node {
                                        id
                                        profile {
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
"""

SINGLE_COMMENT_MENTIONS = """
    query SingleCommentMentions($id: ID!) {
        node(id: $id) {
            ... on Comment {
                mentionsCount
                mentions(first: 10) {
                    edges {
                        node {
                            id
                            profile {
                                id
                            }
                        }
                    }
                }
            }
        }
    }
"""


def test_mentions_resolver_returns_persisted_mentions(graphql_user_client) -> None:
    comment = CommentFactory()
    a = ProfileFactory()
    b = ProfileFactory()
    seed_mentions(comment, [a, b])

    response = graphql_user_client(SINGLE_COMMENT_MENTIONS, variables={"id": comment.relay_id})

    payload = response.json()["data"]["node"]
    assert payload["mentionsCount"] == 2
    assert {edge["node"]["profile"]["id"] for edge in payload["mentions"]["edges"]} == {
        a.relay_id,
        b.relay_id,
    }


def test_paginated_comments_with_mentions_does_not_explode_query_count(
    graphql_user_client,
) -> None:
    """Regression guard for N+1 on the `mentions` connection.

    With 5 comments each carrying 3 mentions, the resolver batches the
    whole tree via the optimizer hook on `MentionsInterface.mentions`:
    - One SELECT for the consumer (Comment) page.
    - One SELECT for the consumers' `document` GenericRelation rows.
    - One SELECT for all mentions targeting those documents.
    - One SELECT for all referenced Profiles (annotated with their
      `mapped_public_id` so the relay-id resolver does not re-query
      DocumentId per row).

    The ceiling trips if the resolver reverts to per-mention joins (which
    would scale as `parents * mentions = 15 + overhead`).

    The ceiling also includes the project's `NestedConnectionInfoProxy`
    pattern, where the outer `optimize_single` (from `node(id: …)`) and
    the inner `DjangoConnectionField` independently page + prefetch the
    nested `comments` connection. That duplication costs ~5 fixed
    queries regardless of mentions count.
    """
    target = CommentFactory()
    profiles = [ProfileFactory() for _ in range(3)]
    children = [CommentFactory(in_reply_to=target) for _ in range(5)]
    for child in children:
        seed_mentions(child, profiles)

    target_id = target.relay_id  # resolve outside the capture

    # Cold ContentType cache (the helper clears it), so the count doesn't depend on test order.
    # Dropping the `mentions` optimizer hook re-introduces a per-comment fan-out of 9 queries
    # (DocumentId lookup + Mention COUNT + page + 3 Mention node fetches + 3 Profile DocumentId
    # lookups), 45 for 5 comments. If this trips, read the captured SQL before bumping.
    with assert_max_queries(
        17,
        hint=(
            "the resolver dropped the optimizer hook, the Profile prefetch lost its "
            "`mapped_public_id` annotation, or the consumer model removed "
            "`document = GenericRelation(DocumentId)`"
        ),
    ):
        response = graphql_user_client(
            COMMENTS_LIST_WITH_MENTIONS, variables={"targetId": target_id}
        )

    assert "errors" not in response.json(), response.json()


def test_is_mentioning_profile_returns_true_when_mention_exists(graphql_user_client) -> None:
    comment = CommentFactory()
    profile = ProfileFactory()
    seed_mentions(comment, [profile])

    query = """
        query IsMentioning($id: ID!, $profileId: ID!) {
            node(id: $id) {
                ... on Comment {
                    isMentioningProfile(profileId: $profileId)
                }
            }
        }
    """
    response = graphql_user_client(
        query, variables={"id": comment.relay_id, "profileId": profile.relay_id}
    )

    assert response.json()["data"]["node"]["isMentioningProfile"] is True


def test_is_mentioning_profile_returns_false_when_no_mention(graphql_user_client) -> None:
    comment = CommentFactory()
    profile = ProfileFactory()

    query = """
        query IsMentioning($id: ID!, $profileId: ID!) {
            node(id: $id) {
                ... on Comment {
                    isMentioningProfile(profileId: $profileId)
                }
            }
        }
    """
    response = graphql_user_client(
        query, variables={"id": comment.relay_id, "profileId": profile.relay_id}
    )

    assert response.json()["data"]["node"]["isMentioningProfile"] is False
