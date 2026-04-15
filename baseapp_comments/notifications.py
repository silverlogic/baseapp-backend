import swapper
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from baseapp_core.plugins import shared_services

Comment = swapper.load_model("baseapp_comments", "Comment")
User = get_user_model()


@shared_task
def send_reply_created_notification(comment_pk):
    if service := shared_services.get("notifications"):
        comment = Comment.objects.get(pk=comment_pk)
        sender = getattr(comment, "profile", None) or comment.user
        service.send_notification(
            add_to_history=True,
            send_push=True,
            send_email=True,
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
def send_comment_created_notification(comment_pk, recipient_id):
    if service := shared_services.get("notifications"):
        comment = Comment.objects.get(pk=comment_pk)
        recipient = User.objects.get(pk=recipient_id)
        sender = getattr(comment, "profile", None) or comment.user
        service.send_notification(
            add_to_history=True,
            send_push=True,
            send_email=True,
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
