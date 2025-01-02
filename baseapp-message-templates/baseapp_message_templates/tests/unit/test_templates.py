import pytest

import baseapp_message_templates.tests.factories as f
from baseapp_message_templates.custom_templates import get_full_copy_template
from baseapp_message_templates.email_utils import (
    send_sendgrid_email,
    send_template_email,
)
from baseapp_message_templates.models import EmailTemplate
from baseapp_message_templates.sendgrid import get_personalization
from baseapp_message_templates.sms_utils import get_sms_message


@pytest.mark.django_db
class TestEmailTemplates:
    @pytest.fixture
    def email_template(self):
        return f.EmailTemplateFactory(name="Test Template", sendgrid_template_id="1234")

    @pytest.fixture
    def english_translation(self, email_template):
        return f.TemplateTranslationFactory(
            target=email_template,
            language="en",
            subject="This is a test",
            html_content="<p>Hello</p>",
        )

    @pytest.fixture
    def spanish_translation(self, email_template):
        return f.TemplateTranslationFactory(
            target=email_template,
            language="es",
            subject="Esto es un teste",
            html_content="<p>Hola</p>",
        )

    @pytest.fixture
    def data(self, email_template, english_translation, spanish_translation):
        return {
            "name": email_template.name,
            "sendgrid_template_id": email_template.sendgrid_template_id,
            "english_subject": english_translation.subject,
            "english_html_content": english_translation.html_content,
            "english_plain_text_content": "Hello",
            "spanish_subject": spanish_translation.subject,
            "spanish_html_content": spanish_translation.html_content,
            "spanish_plain_text_content": "Hola",
        }

    def test_auto_generate_plain_text(self, data):
        template = EmailTemplate.objects.get(name=data["name"])
        _html_content, text_content, subject = get_full_copy_template(template)

        assert text_content == data["english_plain_text_content"]
        assert subject == data["english_subject"]

        _html_content, text_content, subject = get_full_copy_template(template, language="es")
        assert text_content == data["spanish_plain_text_content"]
        assert subject == data["spanish_subject"]

    def test_send_mail(self, outbox, data):
        # If no language is specified, 'send' should use the English translation as default
        send_template_email("Test Template", ["test@test.com"])

        assert len(outbox) == 1

        assert outbox[0].to == ["test@test.com"]
        assert outbox[0].subject == data["english_subject"]
        assert outbox[0].body == data["english_plain_text_content"]
        assert data["english_html_content"] in outbox[0].alternatives[0][0]

    def test_send_mail_translated(self, outbox, data):
        send_template_email("Test Template", ["test@test.com"], language="es")

        assert len(outbox) == 1

        assert outbox[0].to == ["test@test.com"]
        assert outbox[0].subject == data["spanish_subject"]
        assert outbox[0].body == data["spanish_plain_text_content"]
        assert data["spanish_html_content"] in outbox[0].alternatives[0][0]

    def test_email_template_with_no_translations(self):
        EmailTemplate.objects.create(name="Template With No Translations")
        with pytest.raises(Exception) as exc_info:
            send_template_email("Template With No Translations", ["test@test.com"])
        assert str(exc_info.value) == "At least one translation is required to send e-mail"

    def test_send_mail_with_context(self, outbox, data):
        template = EmailTemplate.objects.get(name=data["name"])
        translation = template.translations.filter(language="en").first()
        translation.html_content = "<p>{{content}}</p>"
        translation.plain_text_content = "{{content}}"
        context = {"content": "Test Content"}
        translation.save()
        translation.refresh_from_db()
        template.send(["test@test.com"], context)

        assert len(outbox) == 1

        assert outbox[0].to == ["test@test.com"]
        assert outbox[0].subject == data["english_subject"]
        assert outbox[0].body == context["content"]
        assert outbox[0].alternatives[0][0] == f"<p>{context['content']}</p>"

    def test_get_personalization(self):
        recipient = "test@test.com"
        context = {"message": "Hello!"}
        personalization = get_personalization(recipient, context)

        assert personalization.dynamic_template_data == context
        assert {"email": recipient} in personalization.tos

    def test_send_via_sendgrid(self, outbox, data):
        recipient = "test@test.com"
        context = "Hello!"
        send_sendgrid_email("Test Template", [(recipient, context)])

        assert len(outbox) == 1

    def test_mass_send_via_sendgrid(self, outbox, data):
        recipient_1 = "john@test.com"
        context_1 = "Hello!"
        recipient_2 = "jane@test.com"
        context_2 = "Hi!"
        send_sendgrid_email("Test Template", [(recipient_1, context_1), (recipient_2, context_2)])

        assert len(outbox) == 1
        assert len(outbox[0].personalizations) == 2


@pytest.mark.django_db
class TestSmsTemplates:
    @pytest.fixture
    def data(self):
        template_data = {
            "name": "Test Template",
            "message": "Hello {{ user_name }}",
        }
        self.template = f.SmsTemplateFactory(**template_data)
        return template_data

    def test_get_sms_template_message(self, data):
        context = {"user_name": "Test User"}
        message = get_sms_message(self.template.name, context)

        assert message == "Hello Test User"

    def test_template_does_not_exist(self, caplog):
        context = {"user_name": "Test User"}
        get_sms_message("Nonexistent Template", context)

        assert "Template Nonexistent Template does not exist" in caplog.text
