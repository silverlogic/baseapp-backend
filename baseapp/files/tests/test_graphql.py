import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import CommentFactory

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")

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

COMMENT_FILES_COUNT_QUERY = """
    query CommentFilesCount($id: ID!) {
        node(id: $id) {
            ... on FilesInterface {
                filesCount
            }
        }
    }
"""

COMMENT_IS_FILES_ENABLED_QUERY = """
    query CommentIsFilesEnabled($id: ID!) {
        node(id: $id) {
            ... on FilesInterface {
                isFilesEnabled
            }
        }
    }
"""

COMMENT_FILES_FULL_QUERY = """
    query CommentFilesFull($id: ID!) {
        node(id: $id) {
            ... on FilesInterface {
                filesCount
                isFilesEnabled
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


def test_comment_files_count_interface(graphql_client):
    comment = CommentFactory()
    comment_content_type = ContentType.objects.get_for_model(comment)

    File.objects.create(
        parent_content_type=comment_content_type,
        parent_object_id=comment.pk,
        file_content_type="image/png",
    )
    File.objects.create(
        parent_content_type=comment_content_type,
        parent_object_id=comment.pk,
        file_content_type="image/jpeg",
    )

    response = graphql_client(COMMENT_FILES_COUNT_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    files_count = content["data"]["node"]["filesCount"]
    assert files_count["total"] == 2
    assert files_count["image/png"] == 1
    assert files_count["image/jpeg"] == 1


def test_comment_files_count_interface_empty(graphql_client):
    comment = CommentFactory()

    response = graphql_client(COMMENT_FILES_COUNT_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    files_count = content["data"]["node"]["filesCount"]
    assert files_count["total"] == 0


def test_comment_is_files_enabled_interface(graphql_client):
    comment = CommentFactory()

    response = graphql_client(COMMENT_IS_FILES_ENABLED_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    is_files_enabled = content["data"]["node"]["isFilesEnabled"]
    assert is_files_enabled is True


def test_comment_is_files_enabled_interface_disabled(graphql_client):
    comment = CommentFactory()
    file_target = comment.get_file_target()
    file_target.is_files_enabled = False
    file_target.save()

    response = graphql_client(COMMENT_IS_FILES_ENABLED_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    is_files_enabled = content["data"]["node"]["isFilesEnabled"]
    assert is_files_enabled is False


def test_comment_files_full_interface(graphql_client):
    comment = CommentFactory()
    comment_content_type = ContentType.objects.get_for_model(comment)

    file = File.objects.create(
        parent_content_type=comment_content_type,
        parent_object_id=comment.pk,
        file_content_type="image/png",
        file_name="example.png",
    )

    response = graphql_client(COMMENT_FILES_FULL_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    data = content["data"]["node"]
    assert data["filesCount"]["total"] == 1
    assert data["isFilesEnabled"] is True
    assert len(data["files"]["edges"]) == 1
    assert data["files"]["edges"][0]["node"]["id"] == file.relay_id


def test_comment_files_interface_multiple_files(graphql_client):
    comment = CommentFactory()
    comment_content_type = ContentType.objects.get_for_model(comment)

    for i in range(5):
        File.objects.create(
            parent_content_type=comment_content_type,
            parent_object_id=comment.pk,
            file_name=f"file_{i}.txt",
        )

    response = graphql_client(COMMENT_FILES_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    edges = content["data"]["node"]["files"]["edges"]
    assert len(edges) == 5
