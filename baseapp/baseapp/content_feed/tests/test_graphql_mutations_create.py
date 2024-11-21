import pytest
import swapper

pytestmark = pytest.mark.django_db


ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)

CONTENT_POST_CREATE_GRAPHQL = """
    mutation ContentPostCreateMutation($input: ContentPostCreateInput!) {
        contentPostCreate(input: $input) {
            contentPost {
                node {
                    id
                    content
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
    assert ContentPost.objects.all().count() == 1
    assert ContentPost.objects.filter(
        content=content["data"]["contentPostCreate"]["contentPost"]["node"]["content"]
    ).exists()
    assert ContentPost.objects.all().first().user.pk == django_user_client.user.pk
