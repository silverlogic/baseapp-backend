import logging

from .models import EmailTemplate
from .sendgrid import get_personalization

logger = logging.getLogger(__name__)


def send_template_email(template_name, *args, **kwargs):

    try:
        template = EmailTemplate.objects.get(name=template_name)
        template.send(*args, **kwargs)
    except EmailTemplate.DoesNotExist:
        logger.info(f'Email template "{template_name}" not found.')


def send_sendgrid_email(template_name, recipient_email: str, context={}):
    try:
        template = EmailTemplate.objects.get(name=template_name)
        personalization = get_personalization(recipient_email, context)
        template.send_via_sendgrid(personalization)
    except EmailTemplate.DoesNotExist:
        logger.info(f'Email template "{template_name}" not found.')
