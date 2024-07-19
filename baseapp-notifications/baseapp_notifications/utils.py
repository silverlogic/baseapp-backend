import logging

import swapper
from django.core.mail import send_mail
from django.db.models import Q
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
    push_title=None,
    push_description=None,
    **kwargs,
):
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    notifications = []

    if add_to_history and can_user_receive_notification(
        recipient.id, verb, NotificationSetting.NotificationChannelTypes.IN_APP
    ):
        notifications = notify.send(
            sender=sender,
            recipient=recipient,
            verb=verb,
            action_object=action_object,
            description=description,
            target=target,
            **kwargs,
        )

    if send_email and can_user_receive_notification(
        recipient.id, verb, NotificationSetting.NotificationChannelTypes.EMAIL
    ):
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

    if send_push and can_user_receive_notification(
        recipient.id, verb, NotificationSetting.NotificationChannelTypes.PUSH
    ):
        send_push_notification.delay(
            recipient.id,
            push_title=push_title,
            push_description=push_description or description,
            # TO DO:
            # serialize all objects so devices can use this data if necessary
            **kwargs,
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


def can_user_receive_notification(user_id, verb, channel):
    NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
    user_setting = (
        NotificationSetting.objects.filter(
            Q(channel=channel) | Q(channel=NotificationSetting.NotificationChannelTypes.ALL),
            Q(verb=get_setting_from_verb(verb)) | Q(verb="_ALL_"),
            user_id=user_id,
        )
        .order_by("is_active")
        .first()
    )

    if user_setting:
        return user_setting.is_active
    return True


def get_setting_from_verb(verb):
    """ "
    Returns the setting group from the verb if available, otherwise returns the verb itself
        'CHATS.SEND_MESSAGE' -> 'CHATS'
        'SEND_MESSAGE' -> 'SEND_MESSAGE'
    """
    return verb.split(".")[0] if "." in verb else verb
