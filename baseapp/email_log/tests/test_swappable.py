"""
The test project swaps the log for ``testproject.email_log.EmailLog``, a subclass of the
abstract model with a column of its own, so the whole suite runs against a swapped model.
These tests pin down the swap itself and the package's default model.
"""

from io import StringIO

import pytest
import swapper
from django.core import mail
from django.core.management import call_command
from django.db import models
from django.db.migrations.loader import MigrationLoader
from django.test.utils import isolate_apps

from baseapp.email_log.models import AbstractEmailLog, EmailLog, get_email_log_model
from baseapp.email_log.services import (
    attach_log_metadata,
    get_email_log,
    log_channel_message,
    resend,
    send_logged,
)
from baseapp.email_log.tasks import purge_email_logs, retry_failed_emails

from .helpers import make_email

SETTING = "BASEAPP_EMAIL_LOG_EMAILLOG_MODEL"
SWAPPED = "email_log.EmailLog"


def test_package_default_steps_aside_for_the_swapped_model() -> None:
    from testproject.email_log.models import EmailLog as ProjectEmailLog

    assert get_email_log_model() is ProjectEmailLog
    assert EmailLog._meta.swappable == SETTING
    assert EmailLog._meta.swapped == SWAPPED
    assert ProjectEmailLog._meta.swapped is None


def test_package_migration_creates_the_default_only_when_not_swapped() -> None:
    migration = MigrationLoader(None, ignore_no_migrations=True).get_migration(
        "baseapp_email_log", "0001_initial"
    )
    create = next(op for op in migration.operations if op.name == "EmailLog")

    assert create.options["swappable"] == SETTING


@pytest.mark.django_db
def test_swapping_needs_no_migration_in_the_package() -> None:
    # resend_of points at the swappable name, not "self", which the swapped-out default
    # would resolve to itself and so produce a phantom migration inside the package.
    call_command("makemigrations", "baseapp_email_log", check=True, dry_run=True, stdout=StringIO())


@pytest.mark.django_db
def test_backends_and_services_write_the_swapped_model(django_capture_on_commit_callbacks) -> None:
    Model = get_email_log_model()
    email = attach_log_metadata(make_email(), category="billing")
    email.send()

    log = get_email_log(email)
    assert type(log) is Model
    log.extra_field = "set by the project"
    log.save()
    assert Model.objects.with_status("sent").get().extra_field == "set by the project"

    copy = resend(log)
    assert type(copy) is Model
    assert copy.resend_of == log
    assert list(log.resends.all()) == [copy]

    keyed = send_logged(make_email(), idempotency_key="swapped")
    assert send_logged(make_email(), idempotency_key="swapped") == keyed
    sms = log_channel_message(channel="sms", to="+15555550100", body_text="Hi")
    assert type(sms) is Model
    assert len(mail.outbox) == 3

    assert retry_failed_emails() == 0
    assert purge_email_logs(older_than_days=0) == 3  # the keyed row is kept
    assert list(Model.objects.all()) == [keyed]


def test_setting_swaps_the_model(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_EMAILLOG_MODEL = "users.User"

    assert swapper.get_model_name("baseapp_email_log", "EmailLog") == "users.User"
    assert get_email_log_model()._meta.label == "users.User"
    assert EmailLog._meta.swapped == "users.User"


def test_projects_can_subclass_the_abstract_model(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_EMAILLOG_MODEL = "baseapp_email_log.CustomEmailLog"

    with isolate_apps("baseapp.email_log"):

        class CustomEmailLog(AbstractEmailLog):
            extra_field = models.CharField(max_length=50)

            class Meta(AbstractEmailLog.Meta):
                app_label = "baseapp_email_log"

    field_names = {field.name for field in CustomEmailLog._meta.get_fields()}
    assert {"message", "recipients", "cc", "bcc", "idempotency_key", "extra_field"} <= field_names
    assert CustomEmailLog._meta.swappable == SETTING
    assert CustomEmailLog._meta.swapped is None
    # The default model steps aside, and the queryset helpers come along.
    assert EmailLog._meta.swapped == "baseapp_email_log.CustomEmailLog"
    assert hasattr(CustomEmailLog.objects, "with_status")


@pytest.mark.django_db
def test_plugin_registers_settings_and_schedules() -> None:
    from django.conf import settings

    from baseapp_core.plugins import plugin_registry

    assert settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS is None
    assert settings.BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS is False
    assert settings.BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES == 30
    schedules = plugin_registry.get_all_celery_schedules()
    assert (
        schedules["baseapp_email_log_retry_failed_emails"]["task"]
        == "baseapp.email_log.tasks.retry_failed_emails"
    )
    assert (
        schedules["baseapp_email_log_purge_email_logs"]["task"]
        == "baseapp.email_log.tasks.purge_email_logs"
    )
