from baseapp_message_templates.email_utils import send_template_email
from constance import config
from django.conf import settings


def send_subscription_trial_start_email(email: str):
    context = {
        "trial_days": config.BASEAPP_PAYMENTS_TRIAL_DAYS,
        "url": "{}/results".format(settings.FRONT_URL),
    }
    send_template_email(
        template_name="Trial Started",
        recipients=[email],
        context=context,
    )


def send_subscription_trial_will_end_email(email: str, plan: str):
    context = {"plan": plan}
    send_template_email(
        template_name="Trial Ended",
        recipients=[email],
        context=context,
    )
