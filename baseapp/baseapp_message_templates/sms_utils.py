import logging

from .custom_templates import get_sms_template_message
from .models import SmsTemplate

logger = logging.getLogger(__name__)


def get_sms_message(template_name, context):
    try:
        template = SmsTemplate.objects.get(name=template_name)
        return get_sms_template_message(template, context)
    except SmsTemplate.DoesNotExist:
        logger.error(f"Template {template_name} does not exist")
