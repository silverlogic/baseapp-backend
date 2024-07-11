import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMessage
from sendgrid.helpers.mail import Personalization, To

from .utils import attach_files, chunk

MAX_SENDGRID_PERSONALIZATIONS_PER_API_REQUEST = 1000
logger = logging.getLogger(__name__)


class SengridMessage(EmailMessage):
    def __init__(self, template_id, personalizations: Iterable[Personalization], from_email=None):
        self.personalizations = personalizations
        self.template_id = template_id

        # Django email backend requires at least one recipient to start sending email
        # Real recipients should be configured through Sengdrid personalizations
        to = [settings.DEFAULT_FROM_EMAIL]
        super().__init__(from_email=from_email, to=to)


def send_personalized_mail(copy_template, personalization: Personalization, attachments=[]):
    template_id = copy_template.sendgrid_template_id
    attachments = list(copy_template.static_attachments.all()) + attachments

    mail = SengridMessage(
        template_id=template_id,
        personalizations=[personalization],
    )
    attach_files(mail, attachments)
    return mail.send(fail_silently=True)


def mass_send_personalized_mail(
    copy_template, personalizations: Iterable[Personalization], attachments=[]
):
    """
    Easy wrapper for sending personalized messages of the same Sendgrid template.
    Recipients data is configured through Sendgrid personalizations.
    """
    template_id = copy_template.sendgrid_template_id
    attachments = list(copy_template.static_attachments.all()) + attachments

    for personalizations in chunk(personalizations, MAX_SENDGRID_PERSONALIZATIONS_PER_API_REQUEST):
        mail = SengridMessage(template_id=template_id, personalizations=personalizations)
        attach_files(mail, attachments)
        try:
            mail.send(fail_silently=True)
        except Exception as e:
            logger.error(f"Error: {e} while sending mass email")


def get_personalization(recipient_email: str, context={}):
    personalization = Personalization()
    personalization.add_to(To(recipient_email))
    personalization.dynamic_template_data = context
    return personalization
