"""Tests for CommentableMetadataService and AbstractCommentableMetadata.annotate_queryset."""

import pytest
import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext

from baseapp_core.plugins import shared_services

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
CommentableMetadata = swapper.load_model("baseapp_comments", "CommentableMetadata")


@pytest.fixture
def commentable_metadata_service():
    return shared_services.get("commentable_metadata")


def test_service_name_and_availability(commentable_metadata_service):
    assert commentable_metadata_service.service_name == "commentable_metadata"
    assert commentable_metadata_service.is_available() is True


def test_get_comments_count_reflects_thread(commentable_metadata_service):
    target = CommentFactory()
    parent = CommentFactory(target=target)
    CommentFactory.create_batch(target=target, in_reply_to=parent, size=3)
    reply = CommentFactory(target=target, in_reply_to=parent)

    assert commentable_metadata_service.get_comments_count(parent)["total"] == 4

    CommentFactory(target=target, in_reply_to=reply)

    assert commentable_metadata_service.get_comments_count(parent)["total"] == 4
    assert commentable_metadata_service.get_comments_count(reply)["total"] == 1


def test_commentable_metadata_get_for_object_edge_cases():
    assert CommentableMetadata.get_for_object(None) is None
    assert CommentableMetadata.get_for_object(object()) is None


def test_get_metadata_and_get_or_create(commentable_metadata_service):
    comment = CommentFactory()
    created = commentable_metadata_service.get_or_create_metadata(comment)
    assert created is not None
    fetched = commentable_metadata_service.get_metadata(comment)
    assert fetched is not None
    assert fetched.pk == created.pk


def test_is_comments_enabled_prefers_annotation(commentable_metadata_service):
    comment = CommentFactory(is_comments_enabled=False)
    qs = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk=comment.pk))
    row = qs.get()
    assert commentable_metadata_service.is_comments_enabled(row) is False

    comment_no_ann = Comment.objects.get(pk=comment.pk)
    assert commentable_metadata_service.is_comments_enabled(comment_no_ann) is False


def test_get_comments_count_prefers_annotation(commentable_metadata_service):
    target = CommentFactory()
    parent = CommentFactory(target=target)
    CommentFactory.create_batch(target=target, in_reply_to=parent, size=2)

    qs = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk=parent.pk))
    row = qs.get()
    assert commentable_metadata_service.get_comments_count(row)["total"] == 2


def test_get_comments_count_annotation_none_falls_back_to_default(commentable_metadata_service):
    comment = CommentFactory()
    ct = ContentType.objects.get_for_model(Comment)
    CommentableMetadata.objects.filter(
        target__content_type=ct,
        target__object_id=comment.pk,
    ).delete()

    qs = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk=comment.pk))
    row = qs.get()
    assert row._commentable_comments_count is None
    out = commentable_metadata_service.get_comments_count(row)
    assert out["total"] == 0
    assert out["main"] == 0


def test_annotate_queryset_comment_includes_replies_count_total(commentable_metadata_service):
    target = CommentFactory()
    parent = CommentFactory(target=target)
    CommentFactory.create_batch(target=target, in_reply_to=parent, size=2)

    qs = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk=parent.pk))
    row = qs.get()
    assert hasattr(row, "replies_count_total")
    assert (
        row.replies_count_total == commentable_metadata_service.get_comments_count(parent)["total"]
    )


def test_annotate_queryset_comment_without_metadata_replies_total_zero(
    commentable_metadata_service,
):
    comment = CommentFactory()
    ct = ContentType.objects.get_for_model(Comment)
    CommentableMetadata.objects.filter(
        target__content_type=ct,
        target__object_id=comment.pk,
    ).delete()

    qs = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk=comment.pk))
    row = qs.get()
    assert row.replies_count_total == 0


def test_annotate_queryset_evaluates_in_single_query(commentable_metadata_service):
    target = CommentFactory()
    comments = CommentFactory.create_batch(target=target, size=4)
    ids = [c.pk for c in comments]

    qs = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk__in=ids))
    with CaptureQueriesContext(connection) as ctx:
        rows = list(qs)
    assert len(ctx.captured_queries) == 1
    assert len(rows) == 4
    for r in rows:
        assert hasattr(r, "_commentable_comments_count")
        assert hasattr(r, "_commentable_is_comments_enabled")


def test_service_annotate_queryset_matches_model_classmethod(commentable_metadata_service):
    c = CommentFactory()
    qs1 = commentable_metadata_service.annotate_queryset(Comment.objects.filter(pk=c.pk))
    qs2 = CommentableMetadata.annotate_queryset(Comment.objects.filter(pk=c.pk))
    assert list(qs1.values("pk", "replies_count_total")) == list(
        qs2.values("pk", "replies_count_total")
    )


def test_annotate_queryset_resolves_content_type_after_clear_cache(commentable_metadata_service):
    """One django_content_type lookup when building annotations after clear_cache()."""
    CommentFactory()
    ContentType.objects.clear_cache()

    qs = Comment.objects.all()[:3]
    with CaptureQueriesContext(connection) as ctx:
        commentable_metadata_service.annotate_queryset(qs)
    ct_queries = sum(1 for q in ctx.captured_queries if "django_content_type" in q["sql"])
    assert ct_queries <= 1


@pytest.mark.skipif(
    not apps.is_installed("baseapp_pages"),
    reason="Page model needed for non-Comment annotate_queryset",
)
def test_annotate_queryset_page_has_metadata_but_no_replies_total(commentable_metadata_service):
    from baseapp_pages.tests.factories import PageFactory

    page = PageFactory()
    Page = type(page)
    annotated = commentable_metadata_service.annotate_queryset(Page.objects.filter(pk=page.pk))
    assert "replies_count_total" not in annotated.query.annotations
    row = annotated.get()
    assert hasattr(row, "_commentable_comments_count")
    assert hasattr(row, "_commentable_is_comments_enabled")
