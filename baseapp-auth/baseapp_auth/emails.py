from baseapp_core.deep_links import get_deep_link
from baseapp_core.exceptions import DeepLinkFetchError
from baseapp_message_templates.email_utils import send_template_email
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()
from .tokens import (
    ChangeEmailConfirmTokenGenerator,
    ChangeEmailVerifyTokenGenerator,
    ChangeExpiredPasswordTokenGenerator,
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
    context = {"confirm_url": confirm_url}
    send_template_email(
        template_name="Email Verification", recipients=[user.email], context=context
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
    context = {"reset_url": url}
    send_template_email(template_name="Password Reset", recipients=[info["email"]], context=context)


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
    context = {"confirm_url": url}
    send_template_email(
        template_name="Email Address Change Confirmation",
        recipients=[user.email],
        context=context,
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
    context = {"new_email": user.new_email, "verify_url": url}
    send_template_email(
        template_name="Email Address Change Verification",
        recipients=[user.new_email],
        context=context,
    )


def new_superuser_notification_email(new_superuser, assigner):
    context = {"assigner": assigner.email, "assignee": new_superuser.email}
    superusers = (
        User.objects.filter(is_superuser=True)
        .exclude(email__in=[new_superuser.email, assigner.email])
        .all()
    )
    recipient_list = list(superusers.values_list("email", flat=True))
    send_template_email(
        template_name="Superuser Added",
        recipients=recipient_list,
        context=context,
    )


def remove_superuser_notification_email(non_superuser, assigner):
    context = {"assigner": assigner.email, "assignee": non_superuser.email}
    superusers = (
        User.objects.filter(is_superuser=True)
        .exclude(email__in=[non_superuser.email, assigner.email])
        .all()
    )
    recipient_list = list(superusers.values_list("email", flat=True))
    send_template_email(
        template_name="Superuser Removed",
        recipients=recipient_list,
        context=context,
    )


def send_password_expired_email(user):
    token = ChangeExpiredPasswordTokenGenerator().make_token(user)
    url = settings.FRONT_CHANGE_EXPIRED_PASSWORD_URL.format(token=token)
    context = {"update_password_url": url}
    send_template_email(
        template_name="Password Expired",
        recipients=[user.email],
        context=context,
    )
