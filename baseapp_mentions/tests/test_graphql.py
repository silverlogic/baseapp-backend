"""GraphQL tests for `MentionsInterface` resolvers.

Two concerns:

1. The resolvers (`mentioned_profiles`, `mentions_count`, `is_mentioning_profile`)
   correctly read the through-table.
2. The `mentioned_profiles` connection scales — paginating N parents that each
   expose `mentionedProfiles` does not issue an unbounded number of queries.
   This pins the cost so a future regression (e.g. removing the IN-subquery
   resolver and falling back to per-row joins) trips the test.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from baseapp_comments.tests.factories import CommentFactory
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
                            mentionedProfiles(first: 10) {
                                edges {
                                    node {
                                        id
                                    }
                                }
                            }
                            mentionsCount
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
                mentionedProfiles(first: 10) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        }
    }
"""


def test_mentioned_profiles_resolver_returns_persisted_profiles(graphql_user_client):
    comment = CommentFactory()
    a = ProfileFactory()
    b = ProfileFactory()
    seed_mentions(comment, [a, b])

    response = graphql_user_client(SINGLE_COMMENT_MENTIONS, variables={"id": comment.relay_id})

    payload = response.json()["data"]["node"]
    assert payload["mentionsCount"] == 2
    assert {edge["node"]["id"] for edge in payload["mentionedProfiles"]["edges"]} == {
        a.relay_id,
        b.relay_id,
    }


def test_paginated_comments_with_mentions_does_not_explode_query_count(
    graphql_user_client,
):
    """Regression guard for N+1 on the `mentionedProfiles` connection.

    With 5 comments each carrying 3 mentions, the resolver should batch:
    - One pass to load comments.
    - For each comment, one IN-subquery for Mention.profile_ids and one
      Profile lookup keyed off the IDs (the connection optimiser may merge
      these). Total grows linearly in `parents`, not `parents * mentions`.

    The exact number depends on optimiser internals — we assert an upper
    bound generous enough to absorb optimiser changes but tight enough to
    trip if the resolver reverts to per-mention joins (which would scale
    as `parents * mentions = 15 + overhead`).
    """
    target = CommentFactory()
    profiles = [ProfileFactory() for _ in range(3)]
    children = [CommentFactory(in_reply_to=target) for _ in range(5)]
    for child in children:
        seed_mentions(child, profiles)

    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(
            COMMENTS_LIST_WITH_MENTIONS, variables={"targetId": target.relay_id}
        )

    assert "errors" not in response.json(), response.json()
    # Measured at 9 queries (5 children × 3 mentions × no per-row joins).
    # The IN-subquery resolver collapses what would otherwise be ~15+ queries
    # under a naive per-row implementation. The bound allows ±2 of optimizer
    # drift; if it trips, inspect the diff before just bumping the number.
    assert len(ctx.captured_queries) <= 11, (
        f"Mentions connection issued {len(ctx.captured_queries)} queries (expected ~9). "
        "Likely cause: resolver reverted to per-row joins."
    )


def test_is_mentioning_profile_returns_true_when_mention_exists(graphql_user_client):
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


def test_is_mentioning_profile_returns_false_when_no_mention(graphql_user_client):
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
