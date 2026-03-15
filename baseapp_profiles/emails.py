from datetime import timedelta

import swapper
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from baseapp_core.deep_links import get_deep_link
from baseapp_core.exceptions import DeepLinkFetchError

from .constants import INVITATION_EXPIRATION_DAYS

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


def create_invitation(profile, inviter, invited_email, role=ProfileUserRole.ProfileRoles.MANAGER):
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        invited_user = User.objects.get(email__iexact=invited_email)
    except User.DoesNotExist:
        invited_user = None

    invitation = ProfileUserRole.objects.create(
        profile=profile,
        user=invited_user,
        invited_email=invited_email.lower(),
        role=role,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
        invited_at=timezone.now(),
        invitation_expires_at=timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS),
    )

    invitation.generate_invitation_token()
    invitation.save()

    return invitation


def send_invitation_email(invitation, inviter):
    token = invitation.invitation_token
    fallback_url = settings.FRONT_ACCEPT_INVITATION_URL.format(token=token)

    try:
        deep_link = get_deep_link(
            fallback_url,
            for_ios=settings.IOS_ACCEPT_INVITATION_DEEP_LINK,
            for_android=settings.ANDROID_ACCEPT_INVITATION_DEEP_LINK,
            **{
                "channel": "email",
                "feature": "accept invitation",
                "data": {
                    "type": "accept-invitation",
                    "token": token,
                },
            },
        )
    except DeepLinkFetchError:
        accept_url = fallback_url
    else:
        accept_url = deep_link["url"]

    context = {
        "inviter_name": inviter.get_full_name() or inviter.email,
        "profile_name": invitation.profile.name,
        "role": invitation.get_role_display(),
        "accept_url": accept_url,
        "expiration_date": invitation.invitation_expires_at.strftime("%B %d, %Y"),
    }

    subject = render_to_string("profiles/emails/invitation-subject.txt.j2", context).strip()
    message = render_to_string("profiles/emails/invitation-body.txt.j2", context)
    html_message = render_to_string("profiles/emails/invitation-body.html.j2", context)

    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[invitation.invited_email],
    )
