from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .tokens import ChangeEmailConfirmTokenGenerator, ChangeEmailVerifyTokenGenerator


def send_welcome_email(user):
    context = {'user': user}
    subject = render_to_string('users/emails/welcome-subject.txt.j2', context=context).strip()
    message = render_to_string('users/emails/welcome-body.txt.j2', context=context)
    html_message = render_to_string('users/emails/welcome-body.html.j2', context=context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.email])


def send_password_reset_email(info):
    subject = render_to_string('users/emails/password-reset-subject.txt.j2', info).strip()
    message = render_to_string('users/emails/password-reset-body.txt.j2', info)
    html_message = render_to_string('users/emails/password-reset-body.html.j2', info)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[info['email']])


def send_change_email_confirm_email(user):
    token = ChangeEmailConfirmTokenGenerator().make_token(user)
    context = {
        'url': settings.FRONT_CHANGE_EMAIL_CONFIRM_URL.format(id=user.id, token=token),
        'new_email': user.new_email,
    }
    subject = render_to_string('users/emails/change-email-confirm-subject.txt.j2', context).strip()
    message = render_to_string('users/emails/change-email-confirm-body.txt.j2', context)
    html_message = render_to_string('users/emails/change-email-confirm-body.html.j2', context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.email])


def send_change_email_verify_email(user):
    token = ChangeEmailVerifyTokenGenerator().make_token(user)
    context = {
        'url': settings.FRONT_CHANGE_EMAIL_VERIFY_URL.format(id=user.id, token=token),
    }
    subject = render_to_string('users/emails/change-email-verify-subject.txt.j2', context).strip()
    message = render_to_string('users/emails/change-email-verify-body.txt.j2', context)
    html_message = render_to_string('users/emails/change-email-verify-body.html.j2', context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.new_email])
