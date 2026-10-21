from baseapp.email_log.checks import check_attachment_storage


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
