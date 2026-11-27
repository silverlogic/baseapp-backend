import logging

from .models import EmailTemplate
from .registry import email_templates
from .sendgrid import get_personalization

logger = logging.getLogger(__name__)


def send_template_email(template_name, *args, **kwargs) -> None:
    """Send the ``EmailTemplate`` named ``template_name`` (see ``EmailTemplate.send``).

    A registered name (``register_email_template``) is sent from its template files even when
    it has no row yet; any other missing name is logged and nothing is sent.
    """
    try:
        template = EmailTemplate.objects.get(name=template_name)
    except EmailTemplate.DoesNotExist:
        if not email_templates.is_registered(template_name):
            logger.error(f'Email template "{template_name}" not found.')
            return
        template = EmailTemplate(name=template_name)
    template.send(use_base_template=True, *args, **kwargs)


def send_sendgrid_email(template_name, content=[]) -> None:
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
