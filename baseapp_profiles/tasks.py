import logging

import swapper
from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


@shared_task
def send_invitation_email_task(invitation_id: int, inviter_id: int | None = None) -> bool:
    """
    Send one invitation email; queued on commit when `BASEAPP_PROFILES_INVITATION_ASYNC_SEND`
    is on. An invitation answered, cancelled or deleted in the meantime is skipped.
    """
    from baseapp_profiles.services.invitations import send_invitation_email_now

    ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
    invitation = (
        ProfileUserRole.objects.select_related("profile")
        .filter(pk=invitation_id, status=ProfileUserRole.ProfileRoleStatus.PENDING)
        .first()
    )
    if invitation is None:
        logger.info("Invitation %s is no longer pending; not sending it", invitation_id)
        return False

    inviter = None
    if inviter_id is not None:
        inviter = get_user_model()._default_manager.filter(pk=inviter_id).first()
    return send_invitation_email_now(invitation, inviter=inviter)


@shared_task
def expire_invitations() -> int:
    """Mark overdue PENDING invitations EXPIRED. Scheduled hourly by the plugin's beat entry."""
    from baseapp_profiles.services.invitations import (
        expire_invitations as expire_overdue_invitations,
    )

    return expire_overdue_invitations()
