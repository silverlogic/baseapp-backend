import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save

from baseapp_comments.graphql.subscriptions import OnCommentChange
from baseapp_comments.notifications import (
    send_comment_created_notification,
    send_reply_created_notification,
)

Comment = swapper.load_model("baseapp_comments", "Comment")


def on_comment_saved_graphql_subscription(sender, instance, created, **kwargs):
    if created:
        OnCommentChange.send_created_comment(comment=instance)
    else:
        OnCommentChange.send_updated_comment(comment=instance)


def on_comment_deleted_graphql_subscription(sender, instance, **kwargs):
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


def update_comments_count(sender, instance, created=False, **kwargs):
    default_comments_count = sender._meta.get_field("comments_count").get_default

    if instance.in_reply_to_id:
        qs = sender.objects_visible.filter(in_reply_to_id=instance.in_reply_to_id)

        counts = default_comments_count()
        counts["total"] = qs.count()
        counts["pinned"] = qs.filter(is_pinned=True).count()
        counts["replies"] = counts["total"]
        counts["main"] = counts["total"]

        parent = instance.in_reply_to
        parent.comments_count = counts
        parent.save(update_fields=["comments_count"])

    target = instance.target
    if target and hasattr(target, "comments_count"):
        counts = default_comments_count()

        target_content_type = ContentType.objects.get_for_model(target)
        qs = sender.objects_visible.filter(
            target_content_type=target_content_type, target_object_id=target.pk
        )

        counts["total"] = qs.count()
        counts["replies"] = qs.filter(in_reply_to__isnull=False).count()
        counts["pinned"] = qs.filter(in_reply_to__isnull=True, is_pinned=True).count()
        counts["main"] = counts["total"] - counts["replies"]

        target.comments_count = counts
        target.save(update_fields=["comments_count"])


post_save.connect(update_comments_count, sender=Comment, dispatch_uid="update_comments_count")
post_delete.connect(update_comments_count, sender=Comment, dispatch_uid="update_comments_count")


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
