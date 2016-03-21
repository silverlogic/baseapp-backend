from django.template.loader import render_to_string

from django.core.mail import send_mail


def send_welcome_email(user):
    context = {'user': user}
    subject = render_to_string('users/emails/welcome-subject.txt.j2', context=context).strip()
    message = render_to_string('users/emails/welcome-body.txt.j2', context=context)
    html_message = render_to_string('users/emails/welcome-body.html.j2', context=context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[user.email])
