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
from django.contrib.contenttypes.models import ContentType
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

    The exact number depends on optimiser internals — we assert an upper
    bound generous enough to absorb optimiser changes but tight enough to
    trip if the resolver reverts to per-mention joins (which would scale
    as `parents * mentions = 15 + overhead`).

    The bound also absorbs the project's `NestedConnectionInfoProxy`
    pattern, where the outer `optimize_single` (from `node(id: …)`) and
    the inner `DjangoConnectionField` independently page + prefetch the
    nested `comments` connection. That duplication costs ~5 fixed
    queries regardless of mentions count and is what the +1 above the
    minimal 10 absorbs.
    """
    target = CommentFactory()
    profiles = [ProfileFactory() for _ in range(3)]
    children = [CommentFactory(in_reply_to=target) for _ in range(5)]
    for child in children:
        seed_mentions(child, profiles)

    # Reset the ContentType cache so the count is deterministic regardless of
    # test ordering. A warm cache drops the per-model `get_for_model` lookups
    # (Comment, Mention, Profile) and lands at 16; a cold cache (e.g. after
    # baseapp_follows clears it) adds those 3 and lands at 19. We assert the
    # cold figure so the bound is stable in any ordering.
    ContentType.objects.clear_cache()
    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(
            COMMENTS_LIST_WITH_MENTIONS, variables={"targetId": target.relay_id}
        )

    assert "errors" not in response.json(), response.json()
    # Tight enough to catch a regression that drops the `mentions`
    # optimizer hook (which would re-introduce a per-comment fan-out of
    # 9 queries: DocumentId lookup + Mention COUNT + page + 3 Mention
    # node fetches + 3 Profile DocumentId lookups → 45 queries for 5
    # comments). If this trips, inspect the captured SQL before bumping.
    assert len(ctx.captured_queries) <= 19, (
        f"Mentions connection issued {len(ctx.captured_queries)} queries. "
        "Likely cause: resolver dropped the optimizer hook, "
        "the Profile prefetch lost its `mapped_public_id` annotation, "
        "or the consumer model removed `document = GenericRelation(DocumentId)`."
    )


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
