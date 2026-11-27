from django.test import override_settings

"""
Query-count tests for the `FilesInterface`.

Mirrors `baseapp_reactions/tests/test_graphql_queries_object_reactions.py`: assert
the GraphQL `FilesInterface` resolves in a flat number of database queries
regardless of how many `File` rows point at the target — locks in the
`FilesMetadataService.annotate_queryset` optimisation.
"""

import pytest
import swapper
from django.http import HttpResponse

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.models import DocumentId
from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow

pytestmark = pytest.mark.django_db

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")

# Baseline for `filesCount` + `isFilesEnabled` on one Comment node: 1× relay
# `node()` (documentid + content_type JOIN) + 1× `comments_comment` load with
# `FileTarget` inlined as a Subquery via `pre_optimization_hook`.
# The Comment ContentType lookup counts too: `assert_max_queries` starts from a cold
# ContentType cache, so the number doesn't depend on which tests ran first.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_FILES_INTERFACE_QUERY_COUNT = 3

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


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_files_count_is_flat_regardless_of_file_volume(graphql_client) -> None:
    """`filesCount` is a flat query path: 20 files on the target take the same queries as 3."""
    target = CommentFactory()
    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: attach_files(target, n),
        small=3,
        big=20,
        hint="FilesMetadataService.annotate_queryset is no longer applied to the target",
    )

    # Absolute baseline, catches regressions that bump both sides together.
    with assert_max_queries(EXPECTED_FILES_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["filesCount"]["total"] == 20


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_files_count_zero_when_no_files_does_not_extra_query(graphql_client) -> None:
    """A target with no files resolves in the same budget as one with files: the FileTarget
    row doesn't exist yet and the annotation falls back to the defaults without an extra
    round trip."""
    target = CommentFactory()
    relay_id = target.relay_id

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    with assert_max_queries(EXPECTED_FILES_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["filesCount"]["total"] == 0

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: attach_files(target, n),
        small=0,
        big=3,
        hint="a missing FileTarget row costs an extra query instead of falling to the defaults",
    )


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_listing_comments_with_files_is_flat(graphql_client) -> None:
    """Listing comments that each have files must not fan out one FileTarget query per
    comment: the files annotations ride along in the comment list SELECT via
    `pre_optimization_hook`."""
    target = CommentFactory()
    relay_id = target.relay_id

    def add_replies_with_files(n: int) -> None:
        for _ in range(n):
            attach_files(CommentFactory(target=target), 3)

    def query() -> HttpResponse:
        return graphql_client(COMMENTS_WITH_FILES_LIST_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=add_replies_with_files,
        small=2,
        big=8,
        hint="the comment list lost the files annotations from pre_optimization_hook",
    )

    edges = query().json()["data"]["node"]["comments"]["edges"]
    assert len(edges) == 8
    assert all(edge["node"]["filesCount"]["total"] == 3 for edge in edges)


def test_annotate_queryset_evaluates_in_single_query() -> None:
    """`FileTarget.annotate_queryset` inlines the metadata as Subqueries: the annotated
    queryset evaluates in exactly one SELECT."""
    Comment = CommentFactory._meta.model

    comment_with_files = CommentFactory()
    attach_files(comment_with_files, 2)
    comment_disabled = CommentFactory()
    file_target = comment_disabled.get_file_target()
    file_target.is_files_enabled = False
    file_target.save()
    comment_bare = CommentFactory()

    # Built outside the window: annotating looks up the Comment ContentType.
    queryset = FileTarget.annotate_queryset(
        Comment.objects.filter(pk__in=[comment_with_files.pk, comment_disabled.pk, comment_bare.pk])
    )
    with assert_max_queries(1):
        rows = {row.pk: row for row in queryset}

    assert rows[comment_with_files.pk]._file_target_files_count["total"] == 2
    assert rows[comment_with_files.pk]._file_target_is_files_enabled is True

    assert rows[comment_disabled.pk]._file_target_is_files_enabled is False

    assert rows[comment_bare.pk]._file_target_files_count is None
    assert rows[comment_bare.pk]._file_target_is_files_enabled is True
