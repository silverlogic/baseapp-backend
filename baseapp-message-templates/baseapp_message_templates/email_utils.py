import logging

from .models import EmailTemplate
from .sendgrid import get_personalization

logger = logging.getLogger(__name__)


def send_template_email(template_name, *args, **kwargs):

    try:
        template = EmailTemplate.objects.get(name=template_name)
        template.send(use_base_template=True, *args, **kwargs)
    except EmailTemplate.DoesNotExist:
        logger.error(f'Email template "{template_name}" not found.')


def send_sendgrid_email(template_name, content=[]):
    try:
        template = EmailTemplate.objects.get(name=template_name)
        if len(content) == 0:
            raise ValueError("No personalizations provided.")
        elif len(content) == 1:
            message = content[0]
            recipient, context = message
            personalization = get_personalization(recipient, {"message": context})
            template.send_via_sendgrid(personalization)
        else:
            personalizations = [
                get_personalization(message[0], {"message": message[1]}) for message in content
            ]
            template.mass_send_via_sendgrid(personalizations)
    except EmailTemplate.DoesNotExist:
        logger.error(f'Email template "{template_name}" not found.')
