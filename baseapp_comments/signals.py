import swapper
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal

from baseapp_comments.notifications import (
    send_comment_created_notification,
    send_reply_created_notification,
)
from baseapp_core.models import DocumentId

Comment = swapper.load_model("baseapp_comments", "Comment")

# Kwargs: comment_id (int), target_document_id (int)
comment_created = Signal()

# Kwargs: comment_id (int), target_document_id (int)
comment_deleted = Signal()


def on_comment_saved_graphql_subscription(sender, instance, created, **kwargs):
    from baseapp_comments.graphql.subscriptions import OnCommentChange

    if created:
        OnCommentChange.send_created_comment(comment=instance)
    else:
        OnCommentChange.send_updated_comment(comment=instance)


def on_comment_deleted_graphql_subscription(sender, instance, **kwargs):
    from baseapp_comments.graphql.subscriptions import OnCommentChange

    comment_replay_id = instance.relay_id
    target_relay_id = instance.target.relay_id if instance.target else None
    in_reply_to_relay_id = instance.in_reply_to.relay_id if instance.in_reply_to_id else None

    OnCommentChange.send_delete_comment(
        comment_replay_id=comment_replay_id,
        target_relay_id=target_relay_id,
        in_reply_to_relay_id=in_reply_to_relay_id,
    )


if getattr(settings, "BASEAPP_COMMENTS_ENABLE_GRAPHQL_SUBSCRIPTIONS", True):
    post_save.connect(
        on_comment_saved_graphql_subscription,
        sender=Comment,
        dispatch_uid="on_comment_saved_graphql_subscription",
    )
    post_delete.connect(
        on_comment_deleted_graphql_subscription,
        sender=Comment,
        dispatch_uid="on_comment_deleted_graphql_subscription",
    )


def _recompute_and_save_comments_count(CommentableMetadata, obj, recompute):
    """
    Recompute and persist `comments_count` for `obj` under a row lock to avoid
    read-compute-write races when many comments change concurrently.
    """
    with transaction.atomic():
        metadata = CommentableMetadata.get_or_create_for_object(obj)
        if not metadata:
            return
        metadata = CommentableMetadata.objects.select_for_update().get(pk=metadata.pk)
        metadata.comments_count = recompute()
        metadata.save(update_fields=["comments_count"])


def update_comments_count(sender, instance, created=False, **kwargs):
    CommentableMetadata = swapper.load_model("baseapp_comments", "CommentableMetadata")

    if instance.in_reply_to_id:
        parent = instance.in_reply_to

        def recompute_for_parent():
            qs = sender.objects_visible.filter(in_reply_to_id=instance.in_reply_to_id)
            counts = {
                "total": qs.count(),
                "pinned": qs.filter(is_pinned=True).count(),
                "replies": 0,
                "main": 0,
                "reported": 0,
            }
            counts["replies"] = counts["total"]
            counts["main"] = counts["total"]
            return counts

        _recompute_and_save_comments_count(CommentableMetadata, parent, recompute_for_parent)

    target = instance.target
    if target:

        def recompute_for_target():
            qs = sender.objects_visible.for_target(target, root_only=False)
            total = qs.count()
            replies = qs.filter(in_reply_to__isnull=False).count()
            return {
                "total": total,
                "replies": replies,
                "pinned": qs.filter(in_reply_to__isnull=True, is_pinned=True).count(),
                "main": total - replies,
                "reported": 0,
            }

        _recompute_and_save_comments_count(CommentableMetadata, target, recompute_for_target)


post_save.connect(update_comments_count, sender=Comment, dispatch_uid="update_comments_count")
post_delete.connect(update_comments_count, sender=Comment, dispatch_uid="update_comments_count")


def on_comment_deleted(sender, instance, **kwargs):
    if instance.target:
        target_doc = DocumentId.get_or_create_for_object(instance.target)
        if target_doc:
            comment_deleted.send(
                sender=Comment,
                comment_id=instance.id,
                target_document_id=target_doc.id,
            )


post_delete.connect(on_comment_deleted, sender=Comment, dispatch_uid="on_comment_deleted")


def notify_on_comment_created(sender, instance, created, **kwargs):
    if not getattr(settings, "BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS", True):
        return

    if created and instance.target:
        if not instance.in_reply_to_id:
            user_id = getattr(instance.target, "user_id", None)
            if user_id:
                send_comment_created_notification.delay(instance.pk, user_id)
        else:
            send_reply_created_notification.delay(instance.pk)


post_save.connect(
    notify_on_comment_created, sender=Comment, dispatch_uid="notify_on_comment_created"
)
