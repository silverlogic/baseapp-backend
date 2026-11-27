from typing import TYPE_CHECKING, List

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_prose_editor.fields import ProseEditorField
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel

from .custom_templates import get_full_copy_template
from .registry import email_templates, render_email_template
from .sendgrid import mass_send_personalized_mail, send_personalized_mail
from .utils import attach_files, random_name_in

if TYPE_CHECKING:
    from baseapp_core.graphql import DjangoObjectType


class CaseInsensitiveCharField(models.CharField):
    description = _("Case insensitive character")

    def db_type(self, connection) -> str:
        return "citext"


class EmailTemplate(RelayModel, TimeStampedModel):
    name = CaseInsensitiveCharField(
        _("name"),
        max_length=255,
        unique=True,
        help_text=_("Unique name used to identify this message"),
    )

    # SendGrid
    sendgrid_template_id = models.CharField(
        _("SendGrid template ID"),
        max_length=255,
        blank=True,
        null=True,
    )

    # Core
    subject = models.CharField(
        _("subject"), max_length=255, blank=True, null=True, help_text=_("Email subject line")
    )
    html_content = ProseEditorField(
        _("HTML content"),
        blank=True,
        help_text=_("Text that will be inputted into Template html version"),
        null=True,
        extensions=getattr(settings, "PROSE_EDITOR_EXTENSIONS", None),
        sanitize=getattr(settings, "PROSE_EDITOR_SANITIZE", False),
    )
    # Plain text, never HTML: the prose sanitizer would escape "&" and "<".
    plain_text_content = models.TextField(
        _("plain text content"),
        blank=True,
        help_text=_("Text that will be inputted into Template plain text version"),
    )

    class Meta:
        ordering = ["-id"]
        verbose_name = _("email template")
        verbose_name_plural = _("email templates")
        permissions = [
            ("send_test_emailtemplate", _("Can send test emails of an email template")),
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import EmailTemplateObjectType

        return EmailTemplateObjectType

    @property
    def is_registered(self) -> bool:
        """Whether code registered this name with ``register_email_template``."""
        return email_templates.is_registered(self.name)

    def send_via_sendgrid(self, personalization, attachments=[]) -> None:
        if not self.sendgrid_template_id:
            raise Exception("SendGrid template ID required to send message via SendGrid")
        send_personalized_mail(self, personalization, attachments)

    def mass_send_via_sendgrid(self, personalizations, attachments=[]) -> None:
        if not self.sendgrid_template_id:
            raise Exception("SendGrid template ID required to send message via SendGrid")
        mass_send_personalized_mail(self, personalizations, attachments)

    def send(
        self,
        recipients: List[str],
        context={},
        use_base_template=False,
        extended_with="",
        attachments=[],
        custom_subject="",
    ) -> None:
        """Send this template to ``recipients``.

        A registered name renders through ``render_email_template`` (its files plus this row's
        editable fields), so ``use_base_template`` and ``extended_with`` do not apply: the
        template files own their layout. Other names render this row's content as before.
        """
        if email_templates.is_registered(self.name):
            rendered = render_email_template(
                self.name,
                context,
                recipient=recipients[0] if recipients else None,
                row=self,
            )
            html_content, text_content = rendered.body_html, rendered.body_text
            copy_template_subject = rendered.subject
        else:
            if not self.html_content:
                raise Exception("HTML content required to send e-mail")

            if not use_base_template:
                base_template_route = ""
            else:
                base_template_route = extended_with or settings.DEFAULT_EMAIL_TEMPLATE

            html_content, text_content, copy_template_subject = get_full_copy_template(
                self, context, use_base_template, base_template_route
            )
        subject = custom_subject if custom_subject else copy_template_subject
        mail = EmailMultiAlternatives(
            subject, text_content, from_email=settings.DEFAULT_FROM_EMAIL, to=recipients
        )

        # combine static attachments from template with dynamic attachments
        if html_content:
            mail.attach_alternative(html_content, "text/html")
        static_attachments = list(self.static_attachments.all()) if self.pk else []
        attach_files(mail, static_attachments + list(attachments))

        mail.send()


class Attachment(TimeStampedModel):
    template = models.ForeignKey(
        EmailTemplate,
        verbose_name=_("template"),
        related_name="static_attachments",
        null=False,
        on_delete=models.CASCADE,
    )
    file = models.FileField(_("file"), upload_to=random_name_in("copy_template_file"))
    filename = models.CharField(
        _("filename"),
        max_length=255,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")


class SmsTemplate(TimeStampedModel):
    name = CaseInsensitiveCharField(
        _("name"),
        max_length=255,
        unique=True,
        help_text=_("Unique name used to identify this message"),
    )
    message = models.TextField(
        _("message"), blank=True, null=True, help_text=_("Message to be sent")
    )

    class Meta:
        ordering = ["-id"]
        verbose_name = _("SMS template")
        verbose_name_plural = _("SMS templates")
