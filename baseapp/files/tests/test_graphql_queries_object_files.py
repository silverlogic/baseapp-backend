"""
Query-count tests for the `FilesInterface`.

Mirrors `baseapp_reactions/tests/test_graphql_queries_object_reactions.py`: assert
the GraphQL `FilesInterface` resolves in a flat number of database queries
regardless of how many `File` rows point at the target — locks in the
`FilesMetadataService.annotate_queryset` optimisation.
"""

import pytest
import swapper
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.models import DocumentId

pytestmark = pytest.mark.django_db

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")

# Baseline for `filesCount` + `isFilesEnabled` on one Comment node: 1× relay
# `node()` (documentid + content_type JOIN) + 1× `comments_comment` load with
# `FileTarget` inlined as a Subquery via `pre_optimization_hook`.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_FILES_INTERFACE_QUERY_COUNT = 2

COUNTS_ONLY_QUERY = """
    query GetTarget($id: ID!) {
        node(id: $id) {
            ... on FilesInterface {
                filesCount
                isFilesEnabled
            }
        }
    }
"""

COMMENTS_WITH_FILES_LIST_QUERY = """
    query GetTarget($id: ID!) {
        node(id: $id) {
            ... on CommentsInterface {
                comments(first: 50) {
                    edges {
                        node {
                            id
                            ... on FilesInterface {
                                filesCount
                                isFilesEnabled
                            }
                        }
                    }
                }
            }
        }
    }
"""


def attach_files(target, amount: int) -> None:
    document_id = DocumentId.get_or_create_for_object(target)
    for i in range(amount):
        File.objects.create(
            parent=document_id,
            file_name=f"file-{i}.png",
            file_content_type="image/png",
            upload_status=File.UploadStatus.COMPLETED,
        )


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_files_count_is_flat_regardless_of_file_volume(graphql_client_with_queries):
    """`filesCount` should be a flat query path: regardless of how many `File`
    rows point at the target, the GraphQL query should make the same number of
    DB round-trips."""
    target_small = CommentFactory()
    attach_files(target_small, 3)

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_small.relay_id}
    )
    assert response_small.json()["data"]["node"]["filesCount"]["total"] == 3
    small_count = queries_small.count

    target_big = CommentFactory()
    attach_files(target_big, 20)

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_big.relay_id}
    )
    assert response_big.json()["data"]["node"]["filesCount"]["total"] == 20

    assert queries_big.count == small_count
    # Absolute baseline, catches regressions that bump both sides together.
    assert small_count == EXPECTED_FILES_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_files_count_zero_when_no_files_does_not_extra_query(graphql_client_with_queries):
    """A target with no files should resolve in the same query budget as one
    with files — the FileTarget row simply doesn't exist yet and the annotation
    falls back to the defaults without an extra round-trip."""
    target_with_files = CommentFactory()
    attach_files(target_with_files, 3)

    ContentType.objects.clear_cache()
    response_with, queries_with = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_with_files.relay_id}
    )
    assert response_with.json()["data"]["node"]["filesCount"]["total"] == 3

    target_empty = CommentFactory()

    ContentType.objects.clear_cache()
    response_empty, queries_empty = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_empty.relay_id}
    )
    assert response_empty.json()["data"]["node"]["filesCount"]["total"] == 0

    assert queries_empty.count == queries_with.count
    assert queries_empty.count == EXPECTED_FILES_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_listing_comments_with_files_is_flat(graphql_client_with_queries):
    """Listing comments that each have files must not fan out one FileTarget
    query per comment — the files annotations ride along in the comment list
    SELECT via `pre_optimization_hook`."""
    target_small = CommentFactory()
    for _ in range(2):
        reply = CommentFactory(target=target_small)
        attach_files(reply, 2)

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        COMMENTS_WITH_FILES_LIST_QUERY, variables={"id": target_small.relay_id}
    )
    edges_small = response_small.json()["data"]["node"]["comments"]["edges"]
    assert len(edges_small) == 2
    assert all(edge["node"]["filesCount"]["total"] == 2 for edge in edges_small)
    small_count = queries_small.count

    target_big = CommentFactory()
    for _ in range(8):
        reply = CommentFactory(target=target_big)
        attach_files(reply, 3)

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        COMMENTS_WITH_FILES_LIST_QUERY, variables={"id": target_big.relay_id}
    )
    edges_big = response_big.json()["data"]["node"]["comments"]["edges"]
    assert len(edges_big) == 8
    assert all(edge["node"]["filesCount"]["total"] == 3 for edge in edges_big)

    # The query count must not scale with the number of comments or files.
    assert queries_big.count == small_count


def test_annotate_queryset_evaluates_in_single_query(django_assert_num_queries):
    """`FileTarget.annotate_queryset` inlines the metadata as Subqueries — the
    annotated queryset must evaluate in exactly one SELECT."""
    Comment = CommentFactory._meta.model

    comment_with_files = CommentFactory()
    attach_files(comment_with_files, 2)
    comment_disabled = CommentFactory()
    file_target = comment_disabled.get_file_target()
    file_target.is_files_enabled = False
    file_target.save()
    comment_bare = CommentFactory()

    ContentType.objects.get_for_model(Comment)  # warm the CT cache

    with django_assert_num_queries(1):
        rows = {
            row.pk: row
            for row in FileTarget.annotate_queryset(
                Comment.objects.filter(
                    pk__in=[comment_with_files.pk, comment_disabled.pk, comment_bare.pk]
                )
            )
        }

    assert rows[comment_with_files.pk]._file_target_files_count["total"] == 2
    assert rows[comment_with_files.pk]._file_target_is_files_enabled is True
    assert rows[comment_with_files.pk].files_count_total == 2

    assert rows[comment_disabled.pk]._file_target_is_files_enabled is False

    assert rows[comment_bare.pk]._file_target_files_count is None
    assert rows[comment_bare.pk]._file_target_is_files_enabled is True
    assert rows[comment_bare.pk].files_count_total == 0
