import factory

from baseapp_email_templates.models import EmailTemplate


class EmailTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EmailTemplate
