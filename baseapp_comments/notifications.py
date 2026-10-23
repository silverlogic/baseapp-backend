import swapper
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from baseapp_core.plugins import shared_services

Comment = swapper.load_model("baseapp_comments", "Comment")
User = get_user_model()
app_label = Comment._meta.app_label


def _can_view_target_comments(recipient: User, comment: Comment) -> bool:
    """The notification links to the comment, so only notify users who may read it."""
    return recipient.has_perm(f"{app_label}.view_target_comments", comment.target)


@shared_task
def send_reply_created_notification(comment_pk) -> None:
    if service := shared_services.get("notifications"):
        comment = Comment.objects.get(pk=comment_pk)
        if not _can_view_target_comments(comment.in_reply_to.user, comment):
            return
        sender = getattr(comment, "profile", None) or comment.user
        service.send_notification(
            add_to_history=True,
            send_push=True,
            send_email=getattr(settings, "BASEAPP_COMMENTS_NOTIFICATION_REPLY_EMAIL", True),
            sender=sender,
            recipient=comment.in_reply_to.user,
            verb="COMMENTS.COMMENT_REPLY_CREATED",
            action_object=comment,
            target=comment.in_reply_to,
            level="info",
            description=_("{user} replied to your comment.").format(
                user=str(sender),
            ),
            extra={},
        )


@shared_task
def send_comment_created_notification(comment_pk, recipient_id) -> None:
    if service := shared_services.get("notifications"):
        comment = Comment.objects.get(pk=comment_pk)
        recipient = User.objects.get(pk=recipient_id)
        if not _can_view_target_comments(recipient, comment):
            return
        sender = getattr(comment, "profile", None) or comment.user
        service.send_notification(
            add_to_history=True,
            send_push=True,
            send_email=getattr(settings, "BASEAPP_COMMENTS_NOTIFICATION_CREATED_EMAIL", True),
            sender=sender,
            recipient=recipient,
            verb="COMMENTS.COMMENT_CREATED",
            action_object=comment,
            target=comment.target,
            level="info",
            description=_("{user} left a new comment.").format(
                user=str(sender),
            ),
            extra={},
        )
