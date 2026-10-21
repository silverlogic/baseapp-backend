import pytest
import swapper
from django.db import models
from django.test.utils import isolate_apps

from baseapp.email_log.models import AbstractEmailLog, EmailLog, get_email_log_model

SETTING = "BASEAPP_EMAIL_LOG_EMAILLOG_MODEL"


def test_default_model() -> None:
    assert get_email_log_model() is EmailLog
    assert EmailLog._meta.swappable == SETTING
    assert EmailLog._meta.swapped is None


def test_setting_swaps_the_model(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_EMAILLOG_MODEL = "users.User"

    assert swapper.get_model_name("baseapp_email_log", "EmailLog") == "users.User"
    assert get_email_log_model()._meta.label == "users.User"
    assert EmailLog._meta.swapped == "users.User"


def test_projects_can_subclass_the_abstract_model(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_EMAILLOG_MODEL = "baseapp_email_log.TenantEmailLog"

    with isolate_apps("baseapp.email_log"):

        class TenantEmailLog(AbstractEmailLog):
            tenant = models.CharField(max_length=50)

            class Meta(AbstractEmailLog.Meta):
                app_label = "baseapp_email_log"

    field_names = {field.name for field in TenantEmailLog._meta.get_fields()}
    assert {"message", "recipients", "cc", "bcc", "idempotency_key", "tenant"} <= field_names
    assert TenantEmailLog._meta.swappable == SETTING
    assert TenantEmailLog._meta.swapped is None
    # The default model steps aside, and the queryset helpers come along.
    assert EmailLog._meta.swapped == "baseapp_email_log.TenantEmailLog"
    assert hasattr(TenantEmailLog.objects, "with_status")


@pytest.mark.django_db
def test_plugin_registers_settings_and_schedules() -> None:
    from django.conf import settings

    from baseapp_core.plugins import plugin_registry

    assert settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS is None
    assert settings.BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS is False
    schedules = plugin_registry.get_all_celery_schedules()
    assert (
        schedules["baseapp_email_log_retry_failed_emails"]["task"]
        == "baseapp.email_log.tasks.retry_failed_emails"
    )
    assert (
        schedules["baseapp_email_log_purge_email_logs"]["task"]
        == "baseapp.email_log.tasks.purge_email_logs"
    )
