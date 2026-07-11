import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.models import DocumentId

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
    comment_document_id, _ = DocumentId.objects.get_or_create(
        content_type=comment_content_type,
        object_id=comment.pk,
    )
    file = File.objects.create(
        parent=comment_document_id,
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
    comment_document_id, _ = DocumentId.objects.get_or_create(
        content_type=comment_content_type,
        object_id=comment.pk,
    )

    File.objects.create(
        parent=comment_document_id,
        file_content_type="image/png",
    )
    File.objects.create(
        parent=comment_document_id,
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
    comment_document_id, _ = DocumentId.objects.get_or_create(
        content_type=comment_content_type,
        object_id=comment.pk,
    )

    file = File.objects.create(
        parent=comment_document_id,
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
    comment_document_id, _ = DocumentId.objects.get_or_create(
        content_type=comment_content_type,
        object_id=comment.pk,
    )

    for i in range(5):
        File.objects.create(
            parent=comment_document_id,
            file_name=f"file_{i}.txt",
        )

    response = graphql_client(COMMENT_FILES_QUERY, variables={"id": comment.relay_id})
    content = response.json()

    edges = content["data"]["node"]["files"]["edges"]
    assert len(edges) == 5


FILE_ATTACH_TO_TARGET_MUTATION = """
    mutation FileAttachToTarget($fileRelayIds: [ID]!, $targetObjectId: ID!) {
        fileAttachToTarget(input: {
            fileRelayIds: $fileRelayIds
            targetObjectId: $targetObjectId
        }) {
            attachedFiles {
                node {
                    id
                    fileName
                }
            }
            target {
                ... on FilesInterface {
                    filesCount
                    isFilesEnabled
                }
            }
        }
    }
"""


def test_file_attach_to_target_success(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)

    # Create standalone files (no parent)
    file1 = File.objects.create(
        file_name="file1.txt",
        file_size=1024,
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )
    file2 = File.objects.create(
        file_name="file2.txt",
        file_size=2048,
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file1.relay_id, file2.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" not in content
    data = content["data"]["fileAttachToTarget"]

    # Check attached files
    assert len(data["attachedFiles"]) == 2
    assert data["attachedFiles"][0]["node"]["id"] == file1.relay_id
    assert data["attachedFiles"][0]["node"]["fileName"] == "file1.txt"
    assert data["attachedFiles"][1]["node"]["id"] == file2.relay_id

    # Check target
    assert data["target"]["filesCount"]["total"] == 2
    assert data["target"]["isFilesEnabled"] is True

    # Verify files are attached in database
    file1.refresh_from_db()
    file2.refresh_from_db()
    comment_ct = ContentType.objects.get_for_model(comment)
    comment_doc_id = DocumentId.objects.get(content_type=comment_ct, object_id=comment.pk)
    assert file1.parent == comment_doc_id
    assert file2.parent == comment_doc_id


def test_file_attach_to_target_single_file(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)

    file = File.objects.create(
        file_name="single.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" not in content
    data = content["data"]["fileAttachToTarget"]
    assert len(data["attachedFiles"]) == 1
    assert data["target"]["filesCount"]["total"] == 1


def test_file_attach_to_target_rejects_non_file_relay_id(graphql_user_client, django_user_client):
    """Passing a non-File relay id (e.g. a Comment) is rejected as not_found
    rather than crashing on the permission check / parent assignment."""
    user = django_user_client.user
    comment = CommentFactory(user=user)
    not_a_file = CommentFactory(user=user)

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [not_a_file.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "not_found"


def test_file_attach_to_target_rejects_non_fileable_target(graphql_user_client, django_user_client):
    """A target that does not opt into files (not a FileableModel) is rejected
    with invalid_target instead of committing writes then erroring on the
    FilesInterface payload."""
    from baseapp_profiles.tests.factories import ProfileFactory

    user = django_user_client.user
    # A Profile is a resolvable node but not a FileableModel, so it cannot be a
    # files target.
    profile = ProfileFactory()
    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": profile.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "invalid_target"
    file.refresh_from_db()
    assert file.parent_id is None


def test_file_attach_to_target_requires_authentication(graphql_client):
    comment = CommentFactory()
    file = File.objects.create(file_name="test.txt")

    response = graphql_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "authentication_required"


def test_file_attach_to_target_requires_ownership(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)

    # Create file owned by different user
    from django.contrib.auth import get_user_model

    User = get_user_model()
    other_user = User.objects.create_user(email="other@test.com", password="pass123")
    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=other_user,
    )

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "permission_required"


def test_file_attach_to_target_superuser_can_attach_any_file(
    graphql_user_client, django_user_client
):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    other_user = User.objects.create_user(email="other@test.com", password="pass123")

    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    comment = CommentFactory(user=other_user)
    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=other_user,
    )

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" not in content
    assert len(content["data"]["fileAttachToTarget"]["attachedFiles"]) == 1


def test_file_attach_to_target_files_disabled(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)
    file_target = comment.get_file_target()
    file_target.is_files_enabled = False
    file_target.save()

    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "files_disabled"
    file.refresh_from_db()
    assert file.parent_id is None


def test_file_attach_to_target_already_attached(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment1 = CommentFactory(user=user)
    comment2 = CommentFactory(user=user)

    comment1_ct = ContentType.objects.get_for_model(comment1)
    comment1_doc_id, _ = DocumentId.objects.get_or_create(
        content_type=comment1_ct,
        object_id=comment1.pk,
    )

    # Create file already attached to comment1
    file = File.objects.create(
        file_name="attached.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
        parent=comment1_doc_id,
    )

    # Try to attach to comment2
    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [file.relay_id],
            "targetObjectId": comment2.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "already_attached"


def test_file_attach_to_target_empty_list(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": [],
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    assert content["errors"][0]["extensions"]["code"] == "invalid_input"


def test_file_attach_to_target_invalid_file_id(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)

    response = graphql_user_client(
        FILE_ATTACH_TO_TARGET_MUTATION,
        variables={
            "fileRelayIds": ["RmlsZU9iamVjdFR5cGU6OTk5OTk="],  # Non-existent file ID
            "targetObjectId": comment.relay_id,
        },
    )
    content = response.json()

    assert "errors" in content
    # Error might not have extensions if it's a relay ID parsing error
    if "extensions" in content["errors"][0]:
        assert content["errors"][0]["extensions"]["code"] == "not_found"


FILE_DELETE_MUTATION = """
    mutation FileDeleteMutation($input: FileDeleteInput!) {
        fileDelete(input: $input) {
            deletedId
            parent {
                ... on FilesInterface {
                    filesCount
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_anon_cant_delete_file(graphql_client, django_user_client):
    user = django_user_client.user
    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )

    response = graphql_client(
        FILE_DELETE_MUTATION,
        variables={"input": {"id": file.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert File.objects.count() == 1


def test_user_cant_delete_any_file(graphql_user_client, django_user_client):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    other_user = User.objects.create_user(email="other@test.com", password="pass123")

    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=other_user,
    )

    response = graphql_user_client(
        FILE_DELETE_MUTATION,
        variables={"input": {"id": file.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert File.objects.count() == 1


def test_owner_can_delete_file(django_user_client, graphql_user_client):
    user = django_user_client.user
    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )

    response = graphql_user_client(
        FILE_DELETE_MUTATION,
        variables={"input": {"id": file.relay_id}},
    )
    content = response.json()
    assert content["data"]["fileDelete"]["deletedId"] == file.relay_id
    assert File.objects.count() == 0


def test_superuser_can_delete_file(django_user_client, graphql_user_client):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    other_user = User.objects.create_user(email="other@test.com", password="pass123")

    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=other_user,
    )

    response = graphql_user_client(
        FILE_DELETE_MUTATION,
        variables={"input": {"id": file.relay_id}},
    )
    content = response.json()
    assert content["data"]["fileDelete"]["deletedId"] == file.relay_id
    assert File.objects.count() == 0


def test_user_with_permission_can_delete_file(django_user_client, graphql_user_client):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    User = get_user_model()
    other_user = User.objects.create_user(email="other@test.com", password="pass123")

    app_label = File._meta.app_label
    perm = Permission.objects.get(content_type__app_label=app_label, codename="delete_file")
    django_user_client.user.user_permissions.add(perm)

    file = File.objects.create(
        file_name="test.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=other_user,
    )

    response = graphql_user_client(
        FILE_DELETE_MUTATION,
        variables={"input": {"id": file.relay_id}},
    )
    content = response.json()
    assert content["data"]["fileDelete"]["deletedId"] == file.relay_id
    assert File.objects.count() == 0


def test_update_files_count_after_delete_file(django_user_client, graphql_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)
    comment_content_type = ContentType.objects.get_for_model(comment)
    comment_document_id, _ = DocumentId.objects.get_or_create(
        content_type=comment_content_type,
        object_id=comment.pk,
    )

    file = File.objects.create(
        file_name="test.txt",
        file_content_type="text/plain",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
        parent=comment_document_id,
    )

    # Refresh to get updated files_count
    comment.refresh_from_db()
    assert comment.files_count["total"] == 1
    assert comment.files_count["text/plain"] == 1

    response = graphql_user_client(
        FILE_DELETE_MUTATION,
        variables={"input": {"id": file.relay_id}},
    )
    content = response.json()

    assert content["data"]["fileDelete"]["parent"]["filesCount"]["total"] == 0
    assert File.objects.count() == 0

    comment.refresh_from_db()
    assert comment.files_count["total"] == 0


MY_FILES_QUERY = """
    query MyFiles($noParent: Boolean) {
        myFiles(noParent: $noParent) {
            edges {
                node {
                    id
                    fileName
                }
            }
        }
    }
"""

FILE_NODE_QUERY = """
    query GetFile($id: ID!) {
        file(id: $id) {
            id
            fileName
        }
    }
"""


def test_my_files_includes_own_files(graphql_user_client, django_user_client):
    own_file = File.objects.create(
        file_name="mine.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=django_user_client.user,
    )

    response = graphql_user_client(MY_FILES_QUERY)
    content = response.json()

    assert "errors" not in content
    edges = content["data"]["myFiles"]["edges"]
    assert len(edges) == 1
    assert edges[0]["node"]["id"] == own_file.relay_id
    assert edges[0]["node"]["fileName"] == "mine.txt"


def test_my_files_excludes_other_users_files(graphql_user_client, django_user_client):
    """myFiles is scoped to the authenticated user — other users' files must
    never be returned."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    other_user = User.objects.create_user(email="other@test.com", password="pass123")

    File.objects.create(
        file_name="theirs.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=other_user,
    )
    own_file = File.objects.create(
        file_name="mine.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=django_user_client.user,
    )

    response = graphql_user_client(MY_FILES_QUERY)
    content = response.json()

    assert "errors" not in content
    edges = content["data"]["myFiles"]["edges"]
    assert len(edges) == 1
    assert edges[0]["node"]["id"] == own_file.relay_id


def test_my_files_no_parent_filter(graphql_user_client, django_user_client):
    user = django_user_client.user
    comment = CommentFactory(user=user)
    comment_content_type = ContentType.objects.get_for_model(comment)
    comment_document_id, _ = DocumentId.objects.get_or_create(
        content_type=comment_content_type,
        object_id=comment.pk,
    )

    standalone = File.objects.create(
        file_name="standalone.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
    )
    File.objects.create(
        file_name="attached.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
        parent=comment_document_id,
    )

    response = graphql_user_client(MY_FILES_QUERY, variables={"noParent": True})
    content = response.json()

    assert "errors" not in content
    edges = content["data"]["myFiles"]["edges"]
    assert len(edges) == 1
    assert edges[0]["node"]["id"] == standalone.relay_id


def test_my_files_empty_for_anonymous(graphql_client, django_user_client):
    """Anonymous visitors must not be able to list any files via myFiles."""
    File.objects.create(
        file_name="mine.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=django_user_client.user,
    )

    response = graphql_client(MY_FILES_QUERY)
    content = response.json()

    assert "errors" not in content
    edges = content["data"]["myFiles"]["edges"]
    assert len(edges) == 0


def test_file_node_query_returns_file_for_owner(graphql_user_client, django_user_client):
    file = File.objects.create(
        file_name="mine.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=django_user_client.user,
    )

    response = graphql_user_client(FILE_NODE_QUERY, variables={"id": file.relay_id})
    content = response.json()

    assert "errors" not in content
    assert content["data"]["file"]["id"] == file.relay_id
    assert content["data"]["file"]["fileName"] == "mine.txt"
