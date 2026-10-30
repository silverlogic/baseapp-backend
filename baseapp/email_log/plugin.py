from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class EmailLogPlugin(BaseAppPlugin):
    """
    The Email Log plugin extends djmail: every email keeps its djmail ``Message`` and gains
    a log row with the metadata djmail lacks (cc/bcc, template and context, attachments,
    related object, sender, idempotency key), plus rows for other channels such as SMS.
    """

    @property
    def name(self) -> str:
        return "baseapp_email_log"

    @property
    def package_name(self) -> str:
        return "baseapp.email_log"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            django_extra_settings={
                # Save attachments to the storage below (their names, types and sizes are
                # always logged; djmail keeps its own pickled copy either way).
                "BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS": False,
                # STORAGES alias, or dotted path of a storage class or factory; None is
                # default_storage. Point it at a private storage: attachments are often
                # invoices and other personal documents.
                "BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE": None,
                # Days purge_email_logs keeps rows (and their djmail messages); None keeps all.
                "BASEAPP_EMAIL_LOG_RETENTION_DAYS": None,
                # {category: days}: a shorter retention for some categories (password resets,
                # one-time codes, ...). Applies also while BASEAPP_EMAIL_LOG_RETENTION_DAYS is
                # None; a category cannot keep rows longer than that setting.
                "BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY": {},
                # Whether purge_email_logs deletes rows holding an idempotency key. By default
                # it scrubs them: their content goes, the row and its key stay.
                "BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT": False,
                # Minutes after which retry_failed_emails sends a logged message still a
                # draft (its delivery was never attempted, e.g. a lost Celery task); None
                # leaves drafts alone.
                "BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES": 30,
                # Callable (or dotted path) re-rendering a template on resend:
                # (template, context) -> {"subject", "body_text", "body_html"}.
                "BASEAPP_EMAIL_LOG_RENDERER": None,
            },
            celery_beat_schedules={
                "baseapp_email_log_retry_failed_emails": {
                    "task": "baseapp.email_log.tasks.retry_failed_emails",
                    "schedule": 15 * 60,
                    # 75% of the interval, so a backed-up beat never runs duplicates.
                    "options": {"expires": 11 * 60},
                },
                "baseapp_email_log_purge_email_logs": {
                    "task": "baseapp.email_log.tasks.purge_email_logs",
                    "schedule": 24 * 60 * 60,
                    "options": {"expires": 18 * 60 * 60},
                },
            },
            required_packages=[
                {"djmail": "Stores every email; the log extends its Message"},
            ],
            optional_packages=[],
        )
