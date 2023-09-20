import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import CommentFactory

File = swapper.load_model("baseapp_files", "File")

pytestmark = pytest.mark.django_db

COMMENT_FILES_QUERY = """
    query CommentFiles($id: ID!) {
        node(id: $id) {
            ... on FilesInterface {
                files {
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


def test_comment_files_interface(graphql_client):
    comment = CommentFactory()
    comment_content_type = ContentType.objects.get_for_model(comment)
    file = File.objects.create(
        parent_content_type=comment_content_type,
        parent_object_id=comment.pk,
        file_name="example.txt",
    )

    response = graphql_client(COMMENT_FILES_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    edges = content["data"]["node"]["files"]["edges"]
    assert len(edges) == 1
    assert edges[0]["node"]["id"] == file.relay_id
