from constance import config
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_subscription_trial_start_email(email):
    context = {
        "trial_days": config.BASEAPP_PAYMENTS_TRIAL_DAYS,
        "url": "{}/results".format(settings.FRONT_URL),
    }
    subject = render_to_string("users/emails/trial-starts-subject.txt.j2", context=context).strip()
    message = render_to_string("users/emails/trial-starts-body.txt.j2", context=context)
    html_message = render_to_string("users/emails/trial-starts-body.html.j2", context=context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[email],
    )


def send_subscription_trial_will_end_email(email, plan):
    context = {"plan": plan}
    subject = render_to_string("users/emails/trial-ends-subject.txt.j2", context=context).strip()
    message = render_to_string("users/emails/trial-ends-body.txt.j2", context=context)
    html_message = render_to_string("users/emails/trial-ends-body.html.j2", context=context)
    send_mail(
        subject,
        message,
        html_message=html_message,
        from_email=None,
        recipient_list=[email],
    )
