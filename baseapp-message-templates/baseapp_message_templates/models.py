from typing import List

from ckeditor.fields import RichTextField
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.utils.translation import get_language
from model_utils.models import TimeStampedModel

from .custom_templates import get_full_copy_template
from .sendgrid import mass_send_personalized_mail, send_personalized_mail
from .utils import attach_files, random_name_in


class CaseInsensitiveCharField(models.CharField):
    description = "Case insensitive character"

    def db_type(self, connection):
        return "citext"


class TemplateTranslation(TimeStampedModel):
    target_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    language = models.CharField(max_length=10, choices=settings.LANGUAGES, default="en")
    subject = models.CharField(
        max_length=255, blank=True, null=True, help_text="Email subject line"
    )
    html_content = RichTextField(
        blank=True,
        help_text="Text that will be inputted into Template html version",
        null=True,
    )
    plain_text_content = RichTextField(
        blank=True,
        help_text="Text that will be inputted into Template plain text version",
    )

    class Meta:
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id", "language"]),
        ]
        unique_together = [["target_content_type", "target_object_id", "language"]]


class EmailTemplate(TimeStampedModel):
    name = CaseInsensitiveCharField(
        max_length=255,
        unique=True,
        help_text="Unique name used to identify this message",
    )

    # SendGrid
    sendgrid_template_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    # Translations
    translations = GenericRelation(
        TemplateTranslation,
        object_id_field="target_object_id",
        content_type_field="target_content_type",
    )

    class Meta:
        ordering = ["-id"]

    def send_via_sendgrid(self, personalization, attachments=[]):
        if not self.sendgrid_template_id:
            raise Exception("SendGrid template ID required to send message via SendGrid")
        send_personalized_mail(self, personalization, attachments)

    def mass_send_via_sendgrid(self, personalizations, attachments=[]):
        if not self.sendgrid_template_id:
            raise Exception("SendGrid template ID required to send message via SendGrid")
        mass_send_personalized_mail(self, personalizations, attachments)

    def send(
        self,
        recipients: List[str],
        context=None,
        use_base_template=False,
        extended_with="",
        attachments=None,
        custom_subject="",
        language=None,
    ):
        if self.translations.count() == 0:
            raise ValueError("At least one translation is required to send e-mail")

        if attachments is None:
            attachments = []

        if not use_base_template:
            base_template_route = ""
        else:
            base_template_route = extended_with or settings.DEFAULT_EMAIL_TEMPLATE

        language = language or get_language()

        html_content, text_content, copy_template_subject = get_full_copy_template(
            self, context, use_base_template, base_template_route, language
        )
        subject = custom_subject if custom_subject else copy_template_subject
        mail = EmailMultiAlternatives(
            subject, text_content, from_email=settings.DEFAULT_FROM_EMAIL, to=recipients
        )

        # combine static attachments from template with dynamic attachments
        mail.attach_alternative(html_content, "text/html")
        all_attachments = list(self.static_attachments.all()) + attachments
        attach_files(mail, all_attachments)

        mail.send()


class Attachment(TimeStampedModel):
    template = models.ForeignKey(
        EmailTemplate,
        related_name="static_attachments",
        null=False,
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to=random_name_in("copy_template_file"))
    filename = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )


class SmsTemplate(TimeStampedModel):
    name = CaseInsensitiveCharField(
        max_length=255,
        unique=True,
        help_text="Unique name used to identify this message",
    )
    message = models.TextField(blank=True, null=True, help_text="Message to be sent")

    class Meta:
        ordering = ["-id"]
