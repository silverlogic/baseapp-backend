import logging

import swapper
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from baseapp_notifications import send_notification

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
User = get_user_model()


@shared_task
def send_reaction_created_notification(reaction_pk, recipient_id):
    try:
        reaction = Reaction.objects.get(pk=reaction_pk)
        recipient = User.objects.get(pk=recipient_id)
    except (Reaction.DoesNotExist, User.DoesNotExist):
        logging.info("Reaction or recipient not found. Reaction: %s, Recipient: %s")
        return

    send_notification(
        add_to_history=True,
        send_push=True,
        send_email=True,
        sender=reaction.profile or reaction.user,
        recipient=recipient,
        verb="REACTIONS.REACTION_CREATED",
        action_object=reaction,
        target=reaction.target,
        level="info",
        description=_("{user} reacted to your post.").format(
            user=str(reaction.profile or reaction.user),
        ),
        extra={},
    )
