import swapper
from baseapp_notifications import send_notification
from celery import shared_task


@shared_task
def send_reply_created_notification(profile_pk, description):
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    profile = Profile.objects.get(pk=profile_pk)
    user = profile.owner

    send_notification(
        add_to_history=True,
        send_push=True,
        send_email=True,
        sender=user,
        recipient=user,
        verb="PROFILE.PROFILE_UPDATED",
        action_object=profile,
        target=profile,
        level="info",
        description=description,
        extra={},
    )
