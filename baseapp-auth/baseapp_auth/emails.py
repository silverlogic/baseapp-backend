from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.base.deep_links import get_deep_link
from apps.base.exceptions import DeepLinkFetchError

from .tokens import (
    ChangeEmailConfirmTokenGenerator, ChangeEmailVerifyTokenGenerator, ConfirmEmailTokenGenerator
)


def send_welcome_email(user):
    token = ConfirmEmailTokenGenerator().make_token(user)
    confirm_url = settings.FRONT_CONFIRM_EMAIL_URL.format(id=user.pk, token=token)
    context = {
        'user': user,
        'confirm_url': confirm_url}
    subject = render_to_string('users/emails/welcome-subject.txt.j2', context=context).strip()
    message = render_to_string('users/emails/welcome-body.txt.j2', context=context)
    html_message = render_to_string('users/emails/welcome-body.html.j2', context=context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.email])


def send_password_reset_email(info):
    fallback_url = settings.FRONT_FORGOT_PASSWORD_URL.format(token=info['token'])
    payload = {
        'channel': 'email',
        'feature': 'password reset',
        'tags': ['password', 'password reset', 'forgot password'],
        'data': {
            'email': info['email'],
            'token': info['token'],
            '$fallback_url': fallback_url,
            'type': 'forgot-password'
        }
    }
    try:
        r = get_deep_link(**payload)
    except DeepLinkFetchError:
        url = fallback_url
    else:
        url = r['url']
    context = {'url': url}
    subject = render_to_string('users/emails/password-reset-subject.txt.j2', context).strip()
    message = render_to_string('users/emails/password-reset-body.txt.j2', context)
    html_message = render_to_string('users/emails/password-reset-body.html.j2', context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[info['email']])


def send_change_email_confirm_email(user):
    token = ChangeEmailConfirmTokenGenerator().make_token(user)
    fallback_url = settings.FRONT_CHANGE_EMAIL_CONFIRM_URL.format(id=user.id, token=token)
    payload = {
        'channel': 'email',
        'feature': 'change email',
        'tags': ['email', 'change email', 'change email confirm', 'confirm'],
        'data': {
            'user': user.pk,
            'token': token,
            '$fallback_url': fallback_url,
            'type': 'change-email-confirm',
            'new_email': user.new_email
        }
    }
    try:
        r = get_deep_link(**payload)
    except DeepLinkFetchError:
        url = fallback_url
    else:
        url = r['url']
    context = {
        'url': url,
        'new_email': user.new_email,
    }
    subject = render_to_string('users/emails/change-email-confirm-subject.txt.j2', context).strip()
    message = render_to_string('users/emails/change-email-confirm-body.txt.j2', context)
    html_message = render_to_string('users/emails/change-email-confirm-body.html.j2', context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.email])


def send_change_email_verify_email(user):
    token = ChangeEmailVerifyTokenGenerator().make_token(user)
    fallback_url = settings.FRONT_CHANGE_EMAIL_VERIFY_URL.format(id=user.id, token=token)
    payload = {
        'channel': 'email',
        'feature': 'change email',
        'tags': ['email', 'change email', 'change email verify', 'verify'],
        'data': {
            'user': user.pk,
            'token': token,
            '$fallback_url': fallback_url,
            'type': 'change-email-verify',
            'new_email': user.new_email
        }
    }
    try:
        r = get_deep_link(**payload)
    except DeepLinkFetchError:
        url = fallback_url
    else:
        url = r['url']
    context = {
        'url': url,
    }
    subject = render_to_string('users/emails/change-email-verify-subject.txt.j2', context).strip()
    message = render_to_string('users/emails/change-email-verify-body.txt.j2', context)
    html_message = render_to_string('users/emails/change-email-verify-body.html.j2', context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.new_email])
