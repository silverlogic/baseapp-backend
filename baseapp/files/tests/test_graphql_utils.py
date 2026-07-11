"""Unit tests for baseapp.files.graphql.utils.attach_files_from_relay_ids."""

import pytest
import swapper
from django.contrib.auth import get_user_model
from graphql.error import GraphQLError

from baseapp.files.graphql.utils import attach_files_from_relay_ids
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.models import DocumentId

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")
User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> "User":
    return User.objects.create_user(email="owner@example.com", password="testpass123")


def create_file(user: "User", parent: DocumentId = None, file_name: str = "file.txt") -> "File":
    """Create a completed file owned by the given user."""
    return File.objects.create(
        file_name=file_name,
        upload_status=File.UploadStatus.COMPLETED,
        created_by=user,
        parent=parent,
    )


def test_attaches_files_to_parent(user):
    """Provided relay ids are attached to the parent's DocumentId."""
    comment = CommentFactory(user=user)
    file1 = create_file(user, file_name="a.txt")
    file2 = create_file(user, file_name="b.txt")

    attach_files_from_relay_ids(comment, [file1.relay_id, file2.relay_id], user)

    parent_document_id = DocumentId.get_or_create_for_object(comment)
    file1.refresh_from_db()
    file2.refresh_from_db()
    assert file1.parent == parent_document_id
    assert file2.parent == parent_document_id


def test_noop_for_none_and_empty_list(user):
    """None or an empty list of ids is a no-op."""
    comment = CommentFactory(user=user)

    assert attach_files_from_relay_ids(comment, None, user) is None
    assert attach_files_from_relay_ids(comment, [], user) is None


def test_skips_files_already_attached_to_same_parent(user):
    """Files already attached to the parent are left untouched."""
    comment = CommentFactory(user=user)
    parent_document_id = DocumentId.get_or_create_for_object(comment)
    file_obj = create_file(user, parent=parent_document_id)

    attach_files_from_relay_ids(comment, [file_obj.relay_id], user)

    file_obj.refresh_from_db()
    assert file_obj.parent == parent_document_id
    assert comment.files.count() == 1


def test_moves_file_from_previous_parent_and_recounts(user):
    """A file attached to another parent is moved and the old parent's count updates."""
    old_comment = CommentFactory(user=user)
    new_comment = CommentFactory(user=user)
    old_document_id = DocumentId.get_or_create_for_object(old_comment)
    file_obj = create_file(user, parent=old_document_id)

    attach_files_from_relay_ids(new_comment, [file_obj.relay_id], user)

    file_obj.refresh_from_db()
    assert file_obj.parent == DocumentId.get_or_create_for_object(new_comment)

    old_file_target = FileTarget.objects.get(target=old_document_id)
    assert old_file_target.files_count["total"] == 0


def test_missing_file_raises_not_found(user):
    """A relay id that doesn't resolve to a File raises a not_found error."""
    comment = CommentFactory(user=user)
    # The comment's relay id resolves to a pk with no matching File row.
    with pytest.raises(GraphQLError) as exc_info:
        attach_files_from_relay_ids(comment, [comment.relay_id], user)

    assert exc_info.value.extensions["code"] == "not_found"


def test_deleted_file_relay_id_raises_not_found(user):
    """A relay id whose file (and DocumentId) was deleted raises the same
    not_found GraphQLError as a missing File row."""
    comment = CommentFactory(user=user)
    file_obj = create_file(user)
    relay_id = file_obj.relay_id
    file_obj.delete()

    with pytest.raises(GraphQLError) as exc_info:
        attach_files_from_relay_ids(comment, [relay_id], user)

    assert exc_info.value.extensions["code"] == "not_found"


def test_non_owner_cannot_attach(user):
    """A user cannot attach files created by someone else."""
    other_user = User.objects.create_user(email="other@example.com", password="testpass123")
    comment = CommentFactory(user=user)
    file_obj = create_file(other_user)

    with pytest.raises(GraphQLError) as exc_info:
        attach_files_from_relay_ids(comment, [file_obj.relay_id], user)

    assert exc_info.value.extensions["code"] == "permission_required"
    file_obj.refresh_from_db()
    assert file_obj.parent is None


def test_superuser_can_attach_any_file(user):
    """A superuser can attach files owned by other users."""
    superuser = User.objects.create_user(
        email="admin@example.com", password="testpass123", is_superuser=True
    )
    comment = CommentFactory(user=user)
    file_obj = create_file(user)

    attach_files_from_relay_ids(comment, [file_obj.relay_id], superuser)

    file_obj.refresh_from_db()
    assert file_obj.parent == DocumentId.get_or_create_for_object(comment)


def test_without_user_skips_ownership_check(user):
    """System calls without a user bypass the ownership check."""
    comment = CommentFactory(user=user)
    file_obj = create_file(user)

    attach_files_from_relay_ids(comment, [file_obj.relay_id], None)

    file_obj.refresh_from_db()
    assert file_obj.parent == DocumentId.get_or_create_for_object(comment)


def test_non_owner_cannot_attach_null_creator_file(user):
    """A NULL creator is not an implicit grant — a non-owner cannot re-parent
    (steal) a system/orphan file whose created_by is NULL."""
    comment = CommentFactory(user=user)
    other_parent = CommentFactory(user=user)
    orphan = File.objects.create(
        file_name="orphan.txt",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=None,
        parent=DocumentId.get_or_create_for_object(other_parent),
    )

    with pytest.raises(GraphQLError) as exc_info:
        attach_files_from_relay_ids(comment, [orphan.relay_id], user)

    assert exc_info.value.extensions["code"] == "permission_required"
    orphan.refresh_from_db()
    assert orphan.parent == DocumentId.get_or_create_for_object(other_parent)
