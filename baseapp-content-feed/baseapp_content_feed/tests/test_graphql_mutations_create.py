import pytest

pytestmark = pytest.mark.django_db

from baseapp_content_feed.models import SwappedContentPost as ContentPost

CONTENT_POST_CREATE_GRAPHQL = """
    mutation ContentPostCreateMutation($input: ContentPostCreateInput!) {
        contentPostCreate(input: $input) {
            contentPost {
                node {
                    id
                    content
                    author {
                        email
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


def test_anon_cant_create(graphql_client):
    response = graphql_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={"input": {"content": "Content"}},
    )

    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"

    assert ContentPost.objects.count() == 0


def test_user_can_create(django_user_client, graphql_user_client):
    response = graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={"input": {"content": "Content"}},
    )

    content = response.json()
    assert "errors" not in content
    print(content)
    assert ContentPost.objects.all().count() == 1
    ContentPost.objects.filter(content=content["data"]["contentPostCreate"]["contentPost"]["node"]["content"]).exists()
    assert ContentPost.objects.all().first().author.pk == django_user_client.user.pk
