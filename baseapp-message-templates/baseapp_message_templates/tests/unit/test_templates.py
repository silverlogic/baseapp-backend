import pytest

import baseapp_message_templates.tests.factories as f
from baseapp_message_templates.custom_templates import get_full_copy_template
from baseapp_message_templates.email_utils import (
    send_sendgrid_email,
    send_template_email,
)
from baseapp_message_templates.sendgrid import get_personalization
from baseapp_message_templates.sms_utils import get_sms_message

pytestmark = pytest.mark.django_db


class TestEmailTemplates:
    @pytest.fixture
    def data(self):
        template_data = {
            "name": "Test Template",
            "subject": "This is a test",
            "html_content": "<p>Hello</p>",
            "plain_text_content": "Hello",
            "sendgrid_template_id": "1234",
        }
        self.template = f.EmailTemplateFactory(**template_data)
        return template_data

    def test_auto_generate_plain_text(self, data):
        _html_content, text_content, subject = get_full_copy_template(self.template)

        assert text_content == "Hello"
        assert subject == "This is a test"

    def test_send_mail(self, outbox, data):
        send_template_email("Test Template", ["test@test.com"])

        assert len(outbox) == 1

        assert outbox[0].to == ["test@test.com"]
        assert outbox[0].subject == data["subject"]
        assert outbox[0].body == "Hello"
        assert data["html_content"] in outbox[0].alternatives[0][0]

    def test_send_mail_with_context(self, outbox, data):
        self.template.html_content = "<p>{{content}}</p>"
        self.template.plain_text_content = "{{content}}"
        context = {"content": "Test Content"}
        self.template.send(["test@test.com"], context)

        assert len(outbox) == 1

        assert outbox[0].to == ["test@test.com"]
        assert outbox[0].subject == data["subject"]
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
