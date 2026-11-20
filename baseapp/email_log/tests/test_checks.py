from baseapp.email_log.checks import (
    check_attachment_storage,
    check_retention_by_category,
)


def test_storing_attachments_without_a_storage_warns(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS = True
    settings.BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE = None

    assert [warning.id for warning in check_attachment_storage()] == ["baseapp_email_log.W001"]


def test_no_warning_with_a_storage_or_without_storing(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS = True
    settings.BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE = "private"
    assert check_attachment_storage() == []

    settings.BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS = False
    settings.BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE = None
    assert check_attachment_storage() == []


def test_invalid_retention_by_category_warns(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY = {"auth": "14", "mfa": -1, "x": True}
    (warning,) = check_retention_by_category()
    assert warning.id == "baseapp_email_log.W002"
    assert "auth" in warning.msg and "mfa" in warning.msg and "'x'" in warning.msg

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY = [("auth", 14)]
    assert [w.id for w in check_retention_by_category()] == ["baseapp_email_log.W002"]


def test_valid_retention_by_category_does_not_warn(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY = {"auth": 14, "billing": None, "x": 0}
    assert check_retention_by_category() == []

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY = None
    assert check_retention_by_category() == []
