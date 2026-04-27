"""End-to-end tests for `mentioned_profile_ids` on `ContentPostCreate`.

`baseapp.content_feed` only ships a Create mutation upstream. Update / Edit
behaviour is left to downstream projects. The cases below cover the create-time
contract:

- `ContentPostCreate` persists the M2M when `mentionedProfileIds` is provided
  and silently no-ops when omitted.
- The current profile is excluded from the persisted set.
- Malformed Relay IDs are dropped instead of breaking the parent mutation.
- The `mentionedProfiles` connection on `ContentPostObjectType` returns the
  persisted mentions.
"""

import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")


CONTENT_POST_CREATE_GRAPHQL = """
    mutation ContentPostCreateWithMentions($input: ContentPostCreateInput!) {
        contentPostCreate(input: $input) {
            contentPost {
                node {
                    id
                    content
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


def test_content_post_create_persists_mentioned_profiles(django_user_client, graphql_user_client):
    a = ProfileFactory()
    b = ProfileFactory()

    response = graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={
            "input": {
                "content": "hi @a @b",
                "isReactionsEnabled": True,
                "mentionedProfileIds": [a.relay_id, b.relay_id],
            }
        },
    )

    content = response.json()
    assert "errors" not in content
    post = ContentPost.objects.get()
    assert {p.pk for p in post.mentioned_profiles.all()} == {a.pk, b.pk}

    payload = content["data"]["contentPostCreate"]["contentPost"]["node"]
    assert {edge["node"]["id"] for edge in payload["mentionedProfiles"]["edges"]} == {
        a.relay_id,
        b.relay_id,
    }


def test_content_post_create_without_mention_field_persists_no_mentions(graphql_user_client):
    response = graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={
            "input": {
                "content": "no mentions",
                "isReactionsEnabled": True,
            }
        },
    )

    assert "errors" not in response.json()
    post = ContentPost.objects.get()
    assert post.mentioned_profiles.count() == 0


def test_content_post_create_excludes_self_mention(django_user_client, graphql_user_client):
    me = ProfileFactory(owner=django_user_client.user)
    friend = ProfileFactory()

    graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={
            "input": {
                "content": "@me @friend",
                "isReactionsEnabled": True,
                "mentionedProfileIds": [me.relay_id, friend.relay_id],
            }
        },
        headers={"HTTP_CURRENT_PROFILE": me.relay_id},
    )

    post = ContentPost.objects.get()
    assert list(post.mentioned_profiles.values_list("pk", flat=True)) == [friend.pk]


def test_content_post_create_drops_malformed_mention_ids(graphql_user_client):
    real = ProfileFactory()

    graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={
            "input": {
                "content": "tagged",
                "isReactionsEnabled": True,
                "mentionedProfileIds": [real.relay_id, "not-a-real-id", ""],
            }
        },
    )

    post = ContentPost.objects.get()
    assert list(post.mentioned_profiles.values_list("pk", flat=True)) == [real.pk]
