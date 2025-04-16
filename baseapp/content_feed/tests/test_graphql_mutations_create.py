import pytest
import swapper
from django.test.client import MULTIPART_CONTENT

pytestmark = pytest.mark.django_db


ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")

ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")

CONTENT_POST_CREATE_GRAPHQL = """
    mutation ContentPostCreate($input: ContentPostCreateInput!) {
        contentPostCreate(input: $input) {
            contentPost {
                node {
                    id
                    content
                    images {
                      edges {
                            node {
                                pk
                                image
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


def test_user_can_create_post_with_images(
    django_user_client, graphql_user_client, image_djangofile
):
    images = {"images.0": image_djangofile, "images.1": image_djangofile}
    response = graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={"input": {"content": "Content"}},
        content_type=MULTIPART_CONTENT,
        extra={**images},
    )

    content = response.json()

    post = content["data"]["contentPostCreate"]["contentPost"]["node"]
    assert "errors" not in content
    assert ContentPost.objects.all().count() == 1
    assert ContentPost.objects.filter(content=post["content"]).exists()

    assert ContentPost.objects.all().first().user.pk == django_user_client.user.pk

    images = post["images"]["edges"]
    assert ContentPostImage.objects.all().count() == 2
    assert ContentPostImage.objects.filter(id=images[0]["node"]["pk"]).exists()
    assert ContentPostImage.objects.filter(id=images[1]["node"]["pk"]).exists()
