import pytest

from baseapp_message_templates.admin import EmailTemplateAdminForm
from baseapp_message_templates.registry import Placeholder, register_email_template

pytestmark = pytest.mark.django_db


def form_for(**data) -> EmailTemplateAdminForm:
    return EmailTemplateAdminForm(data={"plain_text_content": "", **data})


def test_validates_editable_parts_of_registered_templates() -> None:
    register_email_template(
        "tests/welcome",
        label="Welcome",
        placeholders=[Placeholder("user.first_name")],
        editable=("subject",),
    )
    form = form_for(name="Tests/Welcome", subject="{{ user.password }}")
    assert not form.is_valid()
    assert form.errors["subject"] == ["Unknown placeholder “user.password”."]

    assert form_for(name="tests/welcome", subject="Hi {{ user.first_name }}").is_valid()
    # parts that are not editable are ignored when sending, so they are not checked
    assert form_for(name="tests/welcome", plain_text_content="{% load static %}").is_valid()


def test_unregistered_templates_are_not_checked() -> None:
    assert form_for(name="legacy", subject="{{ anything.at.all }}").is_valid()
