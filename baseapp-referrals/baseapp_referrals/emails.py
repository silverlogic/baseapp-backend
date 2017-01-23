from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from apps.base.deep_links import get_deep_link
from apps.base.exceptions import DeepLinkFetchError


def send_referrals_email(info):
    try:
        deep_link = get_deep_link(
            for_ios=settings.IOS_CONFIRM_EMAIL_DEEP_LINK,
            for_android=settings.ANDROID_CONFIRM_EMAIL_DEEP_LINK,
            **{
                'channel': 'email',
                'feature': 'referral',
                'data': {
                    'type': 'referrals',
                    'id': info['user'].pk,
                    'email': info['email'],

                }
            }
        )
    except DeepLinkFetchError:
        raise serializers.ValidationError(_('We were unable to complete your request, please try again later.'))
    else:
        url = deep_link['url']

    context = {
        'url': url,
        'app_name': settings.PROJECT_VERBOSE_NAME,
    }
    subject = render_to_string('referrals/emails/referrals-subject.txt.j2', context).strip()
    message = render_to_string('referrals/emails/referrals-body.txt.j2', context)
    html_message = render_to_string('referrals/emails/referrals-body.html.j2', context)
    send_mail(subject, message, html_message=html_message, from_email=None, recipient_list=[info['email']])
