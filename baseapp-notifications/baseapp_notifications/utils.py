import logging

from django.core.mail import send_mail
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.text import slugify
from notifications.signals import notify

from .tasks import send_push_notification


def send_notification(
    sender,
    recipient,
    verb,
    description=None,
    action_object=None,
    target=None,
    add_to_history=True,
    send_push=True,
    send_email=True,
    email_subject=None,
    email_message=None,
    **kwargs,
):
    # TO DO:
    # setting = NotificationSettings.objects.filter(user=recipient, verb=verb).first()
    # if setting and not setting.is_active:
    #     return None
    # can also check user agrees to get notification per email or per push, more refined control

    notifications = []

    if add_to_history:
        notifications = notify.send(
            sender=sender,
            recipient=recipient,
            verb=verb,
            action_object=action_object,
            description=description,
            target=target,
            **kwargs,
        )

    if send_email:
        notification = (
            notifications[0][1][0]
            if len(notifications) > 0 and len(notifications[0]) > 1 and len(notifications[0][1]) > 0
            else None
        )

        send_email_notification(
            to=recipient.email,
            context=dict(
                notification=notification,
                sender=sender,
                recipient=recipient,
                verb=verb,
                action_object=action_object,
                description=description,
                target=target,
                add_to_history=add_to_history,
                send_push=send_push,
                email_subject=email_subject or description,
                email_message=email_message or description,
                **kwargs,
            ),
        )

        if notification:
            notification.emailed = True
            notification.save(update_fields=["emailed"])

    if send_push:
        send_push_notification.delay(
            recipient.id,
            dict(
                description=description,
                verb=verb,
                **kwargs
                # TO DO:
                # serialize all objects so devices can use this data if necessary
            ),
        )

    return notifications


def render_verb_template_or_default(verb, context, template_type, extension):
    try:
        return render_to_string(
            f"emails/notifications/{verb}-{template_type}.{extension}.j2",
            context=context,
        )
    except TemplateDoesNotExist:
        logging.warning(
            f"Template emails/notifications/{verb}-{template_type}.{extension}.j2 does not exist, falling back to default template"
        )
        return render_to_string(
            f"emails/notification-{template_type}.{extension}.j2",
            context=context,
        )


def send_email_notification(to, context):
    verb = slugify(context["verb"])

    subject = render_verb_template_or_default(verb, context, "subject", "txt")
    subject = " ".join(subject.strip().split())

    text_message = render_verb_template_or_default(verb, context, "body", "txt")
    html_message = render_verb_template_or_default(verb, context, "body", "html")

    send_mail(
        subject, text_message, html_message=html_message, from_email=None, recipient_list=[to]
    )
