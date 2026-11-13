import pytest

import baseapp_message_templates.tests.factories as f
from baseapp_message_templates.email_utils import send_template_email
from baseapp_message_templates.registry import Placeholder, register_email_template

pytestmark = pytest.mark.django_db


@pytest.fixture
def registered(email_template_files) -> None:
    register_email_template(
        "tests/welcome",
        label="Welcome",
        placeholders=[Placeholder("user.first_name"), "site_name"],
        editable=("subject",),
    )


def test_send_uses_registry(registered, outbox) -> None:
    template = f.EmailTemplateFactory(name="tests/welcome", subject="Hey {{ user.first_name }}")
    template.send(["ada@example.com"], {"user": {"first_name": "Ada"}, "site_name": "Site"})

    assert len(outbox) == 1
    assert outbox[0].subject == "Hey Ada"
    assert outbox[0].body == "Hi Ada, A & B"
    assert outbox[0].alternatives[0][0] == "<p>Hi Ada, A &amp; B</p>"


def test_send_custom_subject_wins(registered, outbox) -> None:
    template = f.EmailTemplateFactory(name="tests/welcome")
    template.send(["ada@example.com"], {"user": {"first_name": "Ada"}}, custom_subject="Custom")
    assert outbox[0].subject == "Custom"


def test_send_template_email_without_a_row(registered, outbox) -> None:
    send_template_email(
        "tests/welcome", ["ada@example.com"], {"user": {"first_name": "Ada"}, "site_name": "S"}
    )
    assert outbox[0].subject == "Welcome, Ada to S"


def test_send_template_email_unknown_name_logs(outbox, caplog) -> None:
    send_template_email("tests/unknown", ["ada@example.com"])
    assert outbox == []
    assert 'Email template "tests/unknown" not found.' in caplog.text


def test_text_only_registered_template_has_no_html(email_template_files, outbox) -> None:
    register_email_template("tests/text-only", label="Text", editable=())
    f.EmailTemplateFactory(name="tests/text-only").send(["ada@example.com"], {"code": "1"})
    assert outbox[0].alternatives == []


def test_plain_text_is_not_sanitized_as_html() -> None:
    template = f.EmailTemplateFactory(name="plain", plain_text_content="A & B < C")
    template.refresh_from_db()
    assert template.plain_text_content == "A & B < C"
    assert str(template) == "plain"
