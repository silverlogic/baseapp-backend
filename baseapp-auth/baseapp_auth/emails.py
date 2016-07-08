from django.core.mail import send_mail
from django.template.loader import render_to_string


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
