import base64
from io import BytesIO

import pytest
import swapper
from django.core.files.images import ImageFile
from django.test.client import MULTIPART_CONTENT

from baseapp_core.tests.fixtures import IMAGE_BASE64

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
                    isReactionsEnabled
                    images {
                      edges {
                            node {
                                id
                                pk
                                image(width:600, height:0){
                                    url
                                }
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
        variables={"input": {"content": "Content", "isReactionsEnabled": True}},
    )

    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"

    assert ContentPost.objects.count() == 0


def test_user_can_create(django_user_client, graphql_user_client):
    response = graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={"input": {"content": "Content", "isReactionsEnabled": True}},
    )

    content = response.json()
    assert "errors" not in content
    assert ContentPost.objects.all().count() == 1
    assert ContentPost.objects.filter(
        content=content["data"]["contentPostCreate"]["contentPost"]["node"]["content"]
    ).exists()
    assert ContentPost.objects.all().first().user.pk == django_user_client.user.pk


def test_user_can_create_post_with_images(django_user_client, graphql_user_client):
    images = {
        "images.0": ImageFile(BytesIO(base64.b64decode(IMAGE_BASE64)), name="image0.png"),
        "images.1": ImageFile(BytesIO(base64.b64decode(IMAGE_BASE64)), name="image1.png"),
    }
    response = graphql_user_client(
        CONTENT_POST_CREATE_GRAPHQL,
        variables={"input": {"content": "Content", "isReactionsEnabled": True}},
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
