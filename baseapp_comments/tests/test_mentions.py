"""End-to-end tests for `mentioned_profile_ids` on `CommentCreate` / `CommentUpdate`.

These exercise the full GraphQL mutation path so the integration between the
`Input` field, `resolve_mentioned_profiles`, the M2M `set(...)` call, and the
`mentioned_profiles` field on `CommentObjectType` stays wired up.

The semantics under test:

- `CommentCreate` persists the M2M when `mentionedProfileIds` is provided and
  silently no-ops when the field is omitted.
- `CommentUpdate` treats `mentionedProfileIds` as a *replace* operation when
  the list is given (including an empty list, which clears all mentions) and
  preserves the existing mentions when the field is omitted (`None`).
- The current profile is excluded from both create and update payloads — the
  resolver hides self-mentions by design.
- The `mentionedProfiles` connection on `CommentObjectType` returns the
  persisted mentions.
"""

import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")


COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreateMutation($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            comment {
                node {
                    id
                    body
                    mentionedProfiles(first: 10) {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


COMMENT_UPDATE_GRAPHQL = """
    mutation CommentUpdateMutation($input: CommentUpdateInput!) {
        commentUpdate(input: $input) {
            comment {
                id
                body
                mentionedProfiles(first: 10) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def _profile_node_ids(payload):
    return {edge["node"]["id"] for edge in payload["mentionedProfiles"]["edges"]}


def test_comment_create_persists_mentioned_profiles(django_user_client, graphql_user_client):
    target = CommentFactory()
    a = ProfileFactory()
    b = ProfileFactory()

    response = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "hi @a @b",
                "mentionedProfileIds": [a.relay_id, b.relay_id],
            }
        },
    )

    content = response.json()
    assert "errors" not in content
    comment = Comment.objects.exclude(pk=target.pk).get()
    assert {p.pk for p in comment.mentioned_profiles.all()} == {a.pk, b.pk}

    payload = content["data"]["commentCreate"]["comment"]["node"]
    assert _profile_node_ids(payload) == {a.relay_id, b.relay_id}


def test_comment_create_without_mention_field_is_a_noop(graphql_user_client):
    target = CommentFactory()

    response = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "no mentions here",
            }
        },
    )

    content = response.json()
    assert "errors" not in content
    comment = Comment.objects.exclude(pk=target.pk).get()
    assert comment.mentioned_profiles.count() == 0


def test_comment_create_with_empty_list_persists_no_mentions(graphql_user_client):
    target = CommentFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "still no mentions",
                "mentionedProfileIds": [],
            }
        },
    )

    comment = Comment.objects.exclude(pk=target.pk).get()
    assert comment.mentioned_profiles.count() == 0


def test_comment_create_excludes_self_mention(django_user_client, graphql_user_client):
    target = CommentFactory()
    me = ProfileFactory(owner=django_user_client.user)
    friend = ProfileFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "profileId": me.relay_id,
                "body": "@me @friend",
                "mentionedProfileIds": [me.relay_id, friend.relay_id],
            }
        },
        headers={"HTTP_CURRENT_PROFILE": me.relay_id},
    )

    comment = Comment.objects.exclude(pk=target.pk).get()
    assert list(comment.mentioned_profiles.values_list("pk", flat=True)) == [friend.pk]


def test_comment_create_drops_malformed_mention_ids(graphql_user_client):
    target = CommentFactory()
    real = ProfileFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "tagged",
                "mentionedProfileIds": [real.relay_id, "not-a-real-id"],
            }
        },
    )

    comment = Comment.objects.exclude(pk=target.pk).get()
    assert list(comment.mentioned_profiles.values_list("pk", flat=True)) == [real.pk]


def test_comment_update_replaces_mentioned_profiles(django_user_client, graphql_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)
    a = ProfileFactory()
    b = ProfileFactory()
    c = ProfileFactory()
    comment.mentioned_profiles.set([a, b])

    graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={
            "input": {
                "id": comment.relay_id,
                "body": "edited",
                "mentionedProfileIds": [c.relay_id],
            }
        },
    )

    comment.refresh_from_db()
    assert list(comment.mentioned_profiles.values_list("pk", flat=True)) == [c.pk]


def test_comment_update_with_empty_list_clears_mentions(django_user_client, graphql_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)
    a = ProfileFactory()
    comment.mentioned_profiles.set([a])

    graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={
            "input": {
                "id": comment.relay_id,
                "body": "edited",
                "mentionedProfileIds": [],
            }
        },
    )

    comment.refresh_from_db()
    assert comment.mentioned_profiles.count() == 0


def test_comment_update_without_mention_field_preserves_existing(
    django_user_client, graphql_user_client
):
    """`None` (field omitted) is the contract for "leave mentions alone" — only an
    explicit list (including `[]`) replaces them."""
    user = django_user_client.user
    comment = CommentFactory(user=user)
    a = ProfileFactory()
    b = ProfileFactory()
    comment.mentioned_profiles.set([a, b])

    graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={
            "input": {
                "id": comment.relay_id,
                "body": "edited body only",
            }
        },
    )

    comment.refresh_from_db()
    assert {p.pk for p in comment.mentioned_profiles.all()} == {a.pk, b.pk}
