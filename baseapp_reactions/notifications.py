import logging

import swapper
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from baseapp_core.plugins import shared_services

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
User = get_user_model()


@shared_task
def send_reaction_created_notification(reaction_pk, recipient_id):
    service = shared_services.get("notifications")
    if not service:
        return

    try:
        reaction = Reaction.objects.get(pk=reaction_pk)
        recipient = User.objects.get(pk=recipient_id)
    except (Reaction.DoesNotExist, User.DoesNotExist):
        logging.info("Reaction or recipient not found. Reaction: %s, Recipient: %s")
        return

    sender = getattr(reaction, "profile", None) or reaction.user

    service.send_notification(
        add_to_history=True,
        send_push=True,
        send_email=getattr(settings, "BASEAPP_REACTIONS_NOTIFICATION_CREATED_EMAIL", True),
        sender=sender,
        recipient=recipient,
        verb="REACTIONS.REACTION_CREATED",
        action_object=reaction,
        target=reaction.target,
        level="info",
        description=_("{user} reacted to your post.").format(
            user=str(sender),
        ),
        extra={},
    )
