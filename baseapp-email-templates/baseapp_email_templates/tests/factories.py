import factory

from baseapp_email_templates.models import EmailTemplate, SmsTemplate


class EmailTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EmailTemplate


class SmsTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SmsTemplate
