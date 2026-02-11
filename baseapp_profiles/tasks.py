import logging

import swapper
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_invitation_email_task(self, invitation_id, inviter_id):
    from django.contrib.auth import get_user_model
    from django.db import transaction

    from baseapp_profiles.emails import send_invitation_email

    User = get_user_model()

    with transaction.atomic():
        try:
            invitation = ProfileUserRole.objects.select_for_update().get(pk=invitation_id)
        except ProfileUserRole.DoesNotExist:
            logger.error(f"Invitation {invitation_id} not found for email sending")
            return {"status": "error", "message": "Invitation not found"}

        try:
            inviter = User.objects.get(pk=inviter_id)
        except User.DoesNotExist:
            logger.error(f"Inviter {inviter_id} not found for invitation {invitation_id}")
            invitation.invitation_delivery_status = ProfileUserRole.InvitationDeliveryStatus.FAILED
            invitation.invitation_last_send_error = "Inviter user not found"
            invitation.save(
                update_fields=["invitation_delivery_status", "invitation_last_send_error"]
            )
            return {"status": "error", "message": "Inviter not found"}

        invitation.invitation_delivery_status = ProfileUserRole.InvitationDeliveryStatus.SENDING
        invitation.invitation_last_sent_at = timezone.now()
        invitation.save(update_fields=["invitation_delivery_status", "invitation_last_sent_at"])

        try:
            send_invitation_email(invitation, inviter)

            invitation.invitation_delivery_status = ProfileUserRole.InvitationDeliveryStatus.SENT
            invitation.invitation_send_attempts += 1
            invitation.invitation_last_send_error = None
            invitation.save(
                update_fields=[
                    "invitation_delivery_status",
                    "invitation_send_attempts",
                    "invitation_last_send_error",
                ]
            )

            logger.info(
                f"Successfully sent invitation email for invitation {invitation_id} "
                f"to {invitation.invited_email}"
            )

            return {
                "status": "success",
                "invitation_id": invitation_id,
                "email": invitation.invited_email,
            }

        except Exception as exc:
            error_message = str(exc)
            logger.error(
                f"Failed to send invitation email for invitation {invitation_id}: {error_message}",
                exc_info=True,
            )

            invitation.invitation_delivery_status = ProfileUserRole.InvitationDeliveryStatus.FAILED
            invitation.invitation_send_attempts += 1
            invitation.invitation_last_send_error = error_message[:1000]
            invitation.save(
                update_fields=[
                    "invitation_delivery_status",
                    "invitation_send_attempts",
                    "invitation_last_send_error",
                ]
            )

            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            else:
                logger.error(
                    f"Max retries reached for invitation {invitation_id}. Email send permanently failed."
                )
                return {
                    "status": "failed",
                    "invitation_id": invitation_id,
                    "error": error_message,
                    "retries": self.request.retries,
                }
