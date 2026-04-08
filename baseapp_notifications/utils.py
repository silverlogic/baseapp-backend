import logging

import swapper
from django.core.mail import send_mail
from django.db.models import Q
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.text import slugify


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
