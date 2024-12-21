import factory

from baseapp_message_templates.models import (
    EmailTemplate,
    SmsTemplate,
    TemplateTranslation,
)


class EmailTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EmailTemplate


class SmsTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SmsTemplate


class TemplateTranslationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateTranslation
