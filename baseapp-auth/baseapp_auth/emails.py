from urllib.parse import urljoin

from baseapp_core.deep_links import get_deep_link
from baseapp_core.exceptions import DeepLinkFetchError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

User = get_user_model()
from .tokens import (
    ChangeEmailConfirmTokenGenerator,
    ChangeEmailVerifyTokenGenerator,
    ConfirmEmailTokenGenerator,
)


def send_welcome_email(user):
    token = ConfirmEmailTokenGenerator().make_token(user)
    web_url = settings.FRONT_CONFIRM_EMAIL_URL.format(id=user.pk, token=token)
    try:
        deep_link = get_deep_link(
            web_url,
            for_ios=settings.IOS_CONFIRM_EMAIL_DEEP_LINK,
            for_android=settings.ANDROID_CONFIRM_EMAIL_DEEP_LINK,
            **{
                "channel": "email",
                "feature": "confirm email",
                "data": {
                    "type": "confirm-email",
                    "user": user.pk,
                    "token": token,
                },
            },
        )
    except DeepLinkFetchError:
        confirm_url = web_url
    else:
        confirm_url = deep_link["url"]
    context = {"user": user, "confirm_url": confirm_url}
    subject = render_to_string("users/emails/welcome-subject.txt.j2", context=context).strip()
    message = render_to_string("users/emails/welcome-body.txt.j2", context=context)
    html_message = render_to_string("users/emails/welcome-body.html.j2", context=context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[user.email],
    )


def send_password_reset_email(info):
    fallback_url = settings.FRONT_FORGOT_PASSWORD_URL.format(token=info["token"])
    try:
        deep_link = get_deep_link(
            fallback_url,
            for_ios=settings.IOS_FORGOT_PASSWORD_DEEP_LINK,
            for_android=settings.ANDROID_FORGOT_PASSWORD_DEEP_LINK,
            **{
                "channel": "email",
                "feature": "password reset",
                "data": {"type": "forgot-password", "token": info["token"]},
            },
        )
    except DeepLinkFetchError:
        url = fallback_url
    else:
        url = deep_link["url"]
    context = {"url": url}
    subject = render_to_string("users/emails/password-reset-subject.txt.j2", context).strip()
    message = render_to_string("users/emails/password-reset-body.txt.j2", context)
    html_message = render_to_string("users/emails/password-reset-body.html.j2", context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[info["email"]],
    )


def send_change_email_confirm_email(user):
    token = ChangeEmailConfirmTokenGenerator().make_token(user)
    fallback_url = settings.FRONT_CHANGE_EMAIL_CONFIRM_URL.format(id=user.id, token=token)
    try:
        deep_link = get_deep_link(
            fallback_url,
            for_ios=settings.IOS_CHANGE_EMAIL_DEEP_LINK,
            for_android=settings.ANDROID_CHANGE_EMAIL_DEEP_LINK,
            **{
                "channel": "email",
                "feature": "change email",
                "data": {
                    "type": "change-email-confirm",
                    "user": user.pk,
                    "token": token,
                },
            },
        )
    except DeepLinkFetchError:
        url = fallback_url
    else:
        url = deep_link["url"]
    context = {"url": url, "new_email": user.new_email}
    subject = render_to_string("users/emails/change-email-confirm-subject.txt.j2", context).strip()
    message = render_to_string("users/emails/change-email-confirm-body.txt.j2", context)
    html_message = render_to_string("users/emails/change-email-confirm-body.html.j2", context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[user.email],
    )


def send_change_email_verify_email(user):
    token = ChangeEmailVerifyTokenGenerator().make_token(user)
    fallback_url = settings.FRONT_CHANGE_EMAIL_VERIFY_URL.format(id=user.id, token=token)
    try:
        deep_link = get_deep_link(
            fallback_url,
            for_ios=settings.IOS_CHANGE_EMAIL_DEEP_LINK,
            for_android=settings.ANDROID_CHANGE_EMAIL_DEEP_LINK,
            **{
                "channel": "email",
                "feature": "change email",
                "data": {
                    "type": "change-email-verify",
                    "user": user.pk,
                    "token": token,
                },
            },
        )
    except DeepLinkFetchError:
        url = fallback_url
    else:
        url = deep_link["url"]
    context = {"url": url}
    subject = render_to_string("users/emails/change-email-verify-subject.txt.j2", context).strip()
    message = render_to_string("users/emails/change-email-verify-body.txt.j2", context)
    html_message = render_to_string("users/emails/change-email-verify-body.html.j2", context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[user.new_email],
    )


def new_superuser_notification_email(new_superuser, assigner):
    context = {"assigner": assigner, "assignee": new_superuser}
    superusers = (
        User.objects.filter(is_superuser=True)
        .exclude(email__in=[new_superuser.email, assigner.email])
        .all()
    )
    recipient_list = list(superusers.values_list("email", flat=True))

    subject = f"{new_superuser.email} has been made superuser by {assigner.email}"
    message = render_to_string(
        "users/emails/new-superuser-notification-email.txt.j2", context=context
    )
    html_message = render_to_string(
        "users/emails/new-superuser-notification-email.html.j2", context=context
    )
    if recipient_list:
        send_mail(
            subject,
            message,
            html_message=html_message,
            from_email=None,
            recipient_list=recipient_list,
        )


def remove_superuser_notification_email(non_superuser, assigner):
    context = {"assigner": assigner, "assignee": non_superuser}
    superusers = (
        User.objects.filter(is_superuser=True)
        .exclude(email__in=[non_superuser.email, assigner.email])
        .all()
    )
    recipient_list = list(superusers.values_list("email", flat=True))

    subject = f"{non_superuser.email} has been removed from superuser by {assigner.email}"
    message = render_to_string(
        "users/emails/remove-superuser-notification-email.txt.j2",
        context=context,
    )
    html_message = render_to_string(
        "users/emails/remove-superuser-notification-email.html.j2",
        context=context,
    )
    if recipient_list:
        send_mail(
            subject,
            message,
            html_message=html_message,
            from_email=None,
            recipient_list=recipient_list,
        )


def send_password_expired_email(user: User):
    context = dict(url=urljoin(settings.URL, reverse("change-expired-password")))
    subject = render_to_string("users/emails/password-expired-subject.txt.j2", context).strip()
    message = render_to_string("users/emails/password-expired-body.txt.j2", context)
    html_message = render_to_string("users/emails/password-expired-body.html.j2", context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[user.email],
    )
