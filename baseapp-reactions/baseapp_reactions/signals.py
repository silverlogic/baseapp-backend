import swapper
from django.conf import settings
from django.db.models.signals import post_save

from baseapp_reactions.notifications import send_reaction_created_notification

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


def notify_on_reaction_created(sender, instance, created, **kwargs):
    if not getattr(settings, "BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS", True):
        return

    if created and instance.target:
        user_id = getattr(instance.target, "user_id", None)
        if user_id:
            send_reaction_created_notification.delay(instance.pk, user_id)


post_save.connect(
    notify_on_reaction_created, sender=Reaction, dispatch_uid="notify_on_reaction_created"
)
