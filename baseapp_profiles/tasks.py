import logging
from datetime import datetime

import swapper
from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


@shared_task
def send_invitation_email_task(
    invitation_id: int,
    inviter_id: int | None = None,
    token: str | None = None,
    released_until: str | None = None,
) -> bool:
    """
    Send one invitation email; queued on commit when `BASEAPP_PROFILES_INVITATION_ASYNC_SEND`
    is on. An invitation answered, cancelled, deleted or past its expiry date in the
    meantime is skipped.

    `token` is the invitation token the email was queued for. A row that has a different
    one by now was resent, and that resend queued (or is holding) its own email, so this
    one is dropped.

    `released_until` (ISO 8601) is set when the email belongs to a release of a held
    invitation: if it cannot be sent, the invitation goes back on hold.
    """
    from baseapp_profiles.services.invitations import (
        _restore_hold,
        awaits_answer,
        send_invitation_email_now,
    )

    ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
    released = datetime.fromisoformat(released_until) if released_until else None
    invitation = ProfileUserRole.objects.select_related("profile").filter(pk=invitation_id).first()
    if invitation is not None and token is not None and invitation.invitation_token != token:
        logger.info("Invitation %s was resent since; not sending the older email", invitation_id)
        return False
    if invitation is None or not awaits_answer(invitation) or invitation.is_invitation_expired():
        logger.info("Invitation %s is no longer pending; not sending it", invitation_id)
        if released is not None:
            # A release that waited in the queue past its expiry date sent nothing: it
            # goes back on hold (if it is still that release) to be released again.
            _restore_hold(invitation_id, token, released)
        return False

    inviter = None
    if inviter_id is not None:
        inviter = get_user_model()._default_manager.filter(pk=inviter_id).first()
    sent = send_invitation_email_now(invitation, inviter=inviter)
    if not sent and released is not None:
        _restore_hold(invitation_id, token, released)
    return sent


@shared_task
def expire_invitations() -> int:
    """Mark overdue PENDING invitations EXPIRED. Scheduled hourly by the plugin's beat entry."""
    from baseapp_profiles.services.invitations import (
        expire_invitations as expire_overdue_invitations,
    )

    return expire_overdue_invitations()
