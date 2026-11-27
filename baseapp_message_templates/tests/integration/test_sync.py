import pytest
from django.apps import apps
from django.core.management import call_command

import baseapp_message_templates.tests.factories as f
from baseapp_message_templates.apps import sync_registered_email_templates
from baseapp_message_templates.models import EmailTemplate
from baseapp_message_templates.registry import (
    register_email_template,
    sync_email_templates,
)

pytestmark = pytest.mark.django_db


def test_creates_blank_rows_once() -> None:
    register_email_template("tests/one", label="One")
    register_email_template("tests/two", label="Two")
    f.EmailTemplateFactory(name="TESTS/TWO", subject="Kept")

    assert sync_email_templates() == 1
    assert sync_email_templates() == 0

    one = EmailTemplate.objects.get(name="tests/one")
    assert (one.subject, one.plain_text_content, one.html_content) == (None, "", None)
    assert EmailTemplate.objects.get(name="tests/two").subject == "Kept"


def test_nothing_registered() -> None:
    assert sync_email_templates() == 0


def test_management_command(capsys) -> None:
    register_email_template("tests/one", label="One")
    call_command("sync_email_templates")
    assert "Created 1 email template row(s)." in capsys.readouterr().out
    assert EmailTemplate.objects.filter(name="tests/one").exists()


def test_post_migrate_handler() -> None:
    register_email_template("tests/one", label="One")
    app_config = apps.get_app_config("baseapp_message_templates")
    sync_registered_email_templates(sender=app_config, using="default", apps=apps)
    assert EmailTemplate.objects.filter(name="tests/one").exists()


def test_post_migrate_handler_respects_database_routers(settings) -> None:
    settings.DATABASE_ROUTERS = [
        "baseapp_message_templates.tests.integration.test_sync.NoMessageTemplatesRouter"
    ]
    register_email_template("tests/one", label="One")
    app_config = apps.get_app_config("baseapp_message_templates")
    sync_registered_email_templates(sender=app_config, using="default", apps=apps)
    assert not EmailTemplate.objects.exists()


class NoMessageTemplatesRouter:
    def allow_migrate(self, db, app_label, **hints) -> bool | None:
        return False if app_label == "baseapp_message_templates" else None


def test_post_migrate_handler_skips_missing_model() -> None:
    class NoModels:
        def get_model(self, *args) -> None:
            raise LookupError

    register_email_template("tests/one", label="One")
    sync_registered_email_templates(sender=None, apps=NoModels())
    assert not EmailTemplate.objects.exists()
