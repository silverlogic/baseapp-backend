import logging

from .models import EmailTemplate

logger = logging.getLogger(__name__)


def send_template_email(
    template_name=None,
    recipient_list=[],
    context={},
    use_base_template=True,
    extended_with="",
    attachments=[],
):

    try:
        template = EmailTemplate.objects.get(name=template_name)

        template.send(
            recipients=recipient_list,
            context=context,
            use_base_template=use_base_template,
            extended_with=extended_with,
            attachments=attachments,
        )
    except EmailTemplate.DoesNotExist:
        logger.info(f'Email template "{template_name}" not found.')
