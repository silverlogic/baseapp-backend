import swapper
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
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


def _broadcast_comment_change(groups: list[str], payload: dict) -> None:
    from baseapp_core.strawberry.subscriptions import broadcast, subscription_group

    for group_name in groups:
        broadcast(subscription_group("OnCommentChange", group_name), payload)


def send_created_comment(comment) -> None:
    groups = ["all"]
    # Replies only reach the parent thread, not the target.
    if comment.in_reply_to_id:
        groups.append(comment.in_reply_to.relay_id)
    elif comment.target_document_id:
        try:
            groups.append(comment.target.relay_id)
        except ObjectDoesNotExist:
            pass
    _broadcast_comment_change(groups, {"created_comment": comment})


def send_updated_comment(comment) -> None:
    groups = ["all"]
    if comment.target_document_id and comment.target and comment.target.relay_id:
        groups.append(comment.target.relay_id)
    if comment.in_reply_to_id:
        groups.append(comment.in_reply_to.relay_id)
    _broadcast_comment_change(groups, {"updated_comment": comment})


def send_deleted_comment(comment_relay_id, target_relay_id, in_reply_to_relay_id) -> None:
    groups = ["all"]
    if target_relay_id:
        groups.append(target_relay_id)
    if in_reply_to_relay_id:
        groups.append(in_reply_to_relay_id)
    _broadcast_comment_change(groups, {"deleted_comment_id": comment_relay_id})


def on_comment_saved_graphql_subscription(sender, instance, created, **kwargs) -> None:
    if created:
        send_created_comment(instance)
    else:
        send_updated_comment(instance)


def on_comment_deleted_graphql_subscription(sender, instance, **kwargs) -> None:
    send_deleted_comment(
        comment_relay_id=instance.relay_id,
        target_relay_id=instance.target.relay_id if instance.target else None,
        in_reply_to_relay_id=instance.in_reply_to.relay_id if instance.in_reply_to_id else None,
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


def _recompute_and_save_comments_count(CommentableMetadata, obj, recompute) -> None:
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


def update_comments_count(sender, instance, created=False, **kwargs) -> None:
    CommentableMetadata = swapper.load_model("baseapp_comments", "CommentableMetadata")

    if instance.in_reply_to_id:
        parent = instance.in_reply_to

        def recompute_for_parent() -> dict[str, int]:
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

        def recompute_for_target() -> dict[str, int]:
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


def on_comment_deleted(sender, instance, **kwargs) -> None:
    if instance.target:
        target_doc = DocumentId.get_or_create_for_object(instance.target)
        if target_doc:
            comment_deleted.send(
                sender=Comment,
                comment_id=instance.id,
                target_document_id=target_doc.id,
            )


post_delete.connect(on_comment_deleted, sender=Comment, dispatch_uid="on_comment_deleted")


def notify_on_comment_created(sender, instance, created, **kwargs) -> None:
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
