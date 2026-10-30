from collections.abc import Iterable
from typing import Any

from constance import config
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import translation

from baseapp_core.deep_links import get_deep_link
from baseapp_core.exceptions import DeepLinkFetchError
from baseapp_core.i18n import group_by_language, user_language

from .tokens import (
    ChangeEmailConfirmTokenGenerator,
    ChangeEmailVerifyTokenGenerator,
    ChangeExpiredPasswordTokenGenerator,
    ConfirmEmailTokenGenerator,
)

User = get_user_model()


def _render(template_name: str, context: dict[str, Any]) -> tuple[str, str, str]:
    """Render subject, text body and HTML body for ``users/emails/<template_name>-*``."""
    subject = render_to_string(f"users/emails/{template_name}-subject.txt.j2", context).strip()
    message = render_to_string(f"users/emails/{template_name}-body.txt.j2", context)
    html_message = render_to_string(f"users/emails/{template_name}-body.html.j2", context)
    return subject, message, html_message


def _send(
    template_name: str, context: dict[str, Any], recipient_list: list[str], user: Any = None
) -> None:
    """Send one email rendered in ``user``'s preferred language."""
    if not recipient_list:
        return
    with user_language(user):
        subject, message, html_message = _render(template_name, context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=recipient_list,
    )


def _send_to_users(template_name: str, context: dict[str, Any], users: Iterable[Any]) -> None:
    """Broadcast to many users, one email per language so each reads it in their own."""
    for language, group in group_by_language(users).items():
        with translation.override(language):
            subject, message, html_message = _render(template_name, context)
        send_mail(
            subject,
            message,
            html_message=html_message,
            from_email=None,
            recipient_list=[user.email for user in group],
        )


def _user_for_email(email: str) -> Any:
    return User.objects.filter(email__iexact=email).first()


def send_welcome_email(user) -> None:
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
    _send("welcome", context, [user.email], user=user)


def send_password_reset_email(info) -> None:
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
    _send("password-reset", context, [info["email"]], user=_user_for_email(info["email"]))


def send_change_email_confirm_email(user) -> None:
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
    _send("change-email-confirm", context, [user.email], user=user)


def send_change_email_verify_email(user) -> None:
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
    _send("change-email-verify", context, [user.new_email], user=user)


def new_superuser_notification_email(new_superuser, assigner) -> None:
    context = {"assigner": assigner, "assignee": new_superuser}
    superusers = User.objects.filter(is_superuser=True).exclude(
        email__in=[new_superuser.email, assigner.email]
    )
    _send_to_users("new-superuser-notification-email", context, superusers)


def remove_superuser_notification_email(non_superuser, assigner) -> None:
    context = {"assigner": assigner, "assignee": non_superuser}
    superusers = User.objects.filter(is_superuser=True).exclude(
        email__in=[non_superuser.email, assigner.email]
    )
    _send_to_users("remove-superuser-notification-email", context, superusers)


def send_password_expired_email(user) -> None:
    token = ChangeExpiredPasswordTokenGenerator().make_token(user)
    url = settings.FRONT_CHANGE_EXPIRED_PASSWORD_URL.format(token=token)
    context = {"url": url}
    _send("password-expired", context, [user.email], user=user)


def send_anonymize_user_success_email(user_email) -> None:
    context = {"user_email": user_email}
    _send("anonymize-user-success", context, [user_email], user=_user_for_email(user_email))

    if not getattr(config, "SEND_USER_ANONYMIZE_EMAIL_TO_SUPERUSERS", False):
        return None
    superusers = User.objects.filter(is_superuser=True).exclude(email__in=[user_email])
    _send_to_users("anonymize-user-success-superuser", context, superusers)


def send_anonymize_user_error_email(user_email) -> None:
    context = {"user_email": user_email}
    _send("anonymize-user-error", context, [user_email], user=_user_for_email(user_email))

    if not getattr(config, "SEND_USER_ANONYMIZE_EMAIL_TO_SUPERUSERS", False):
        return None
    superusers = User.objects.filter(is_superuser=True).exclude(email__in=[user_email])
    _send_to_users("anonymize-user-error-superuser", context, superusers)
