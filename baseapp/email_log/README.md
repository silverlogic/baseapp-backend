# BaseApp Email Log

Extends [djmail](https://github.com/bameda/djmail) with an email log. djmail's `Message` stays
the one store of every email (subject, bodies, from/to, status, exception, sent date, and the
pickled message it retries from). This package adds a row linked one-to-one to each message
holding what djmail does not keep:

- cc, bcc, reply-to and the full To list
- the template key and render context, to re-render on resend
- attachments: name, content type and size, and optionally a copy in a storage of your choice
- the related object (any model, through a generic foreign key) and a label for it
- a free-text category, the user who sent it, the row it re-sends
- an idempotency key, so an email is sent once per key
- the channel: rows for SMS and other channels, which never go through djmail, carry their own
  text and delivery state

It also makes transport errors visible (djmail records them but leaves the message a draft
that is never retried), schedules djmail's retry, purges old rows, and adds an admin with a
resend action.

## Installation

Add the app after `djmail` and route email through one of the logging backends:

```python
INSTALLED_APPS = [
    ...
    "djmail",
    "baseapp.email_log",
]

# Synchronous, like djmail.backends.default.EmailBackend:
EMAIL_BACKEND = "baseapp.email_log.backends.EmailBackend"
# Or through Celery, like djmail.backends.celery.EmailBackend:
# EMAIL_BACKEND = "baseapp.email_log.backends.CeleryEmailBackend"

# The transport, as before:
DJMAIL_REAL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
```

Then `python manage.py migrate baseapp_email_log`.

Nothing else changes for code that sends email: `send_mail`, `EmailMessage.send()`,
`TemplateMail` and every BaseApp package keep working, and each email they send now gets a
log row with its recipients, cc, bcc, reply-to and attachments.

`CeleryEmailBackend` differs from djmail's in one way: the message and its row are written
in the calling process, so the row exists (status `queued`) as soon as `send()` returns, and
the worker only delivers, after the surrounding transaction commits. `send()` returns the
number of messages queued instead of an `AsyncResult`.

## Reading a row

Read every row through the same properties, whatever its channel. Email rows resolve them
from their djmail message, other channels from their own `delivery_*` columns:

| Property | Email row | Other channels |
|---|---|---|
| `subject`, `body_html`, `from_email` | djmail message | empty |
| `body_text` | djmail message | `delivery_body_text` |
| `to` | djmail `to_email` (comma separated) | `delivery_to` |
| `status` | djmail status, mapped (see below) | `delivery_status` |
| `sent_at` | djmail `sent_at` | `delivered_at` |
| `error` | djmail `exception` (the traceback) | `delivery_error` |

`status` is one of `queued`, `sending`, `sent`, `failed`, `discarded`
(`EmailLogStatus`). `baseapp.email_log.status` maps djmail's integers both ways:
`status_from_djmail(30) == "sent"`, `status_to_djmail("failed") == Message.STATUS_FAILED`,
and `djmail_statuses_for("queued")` lists the djmail values that read as `queued` (draft
and pending). Filter on it with the queryset method:

```python
from baseapp.email_log.models import get_email_log_model

EmailLog = get_email_log_model()
EmailLog.objects.with_status("failed")
EmailLog.objects.for_object(invoice)  # rows whose related object is `invoice`
```

An email row whose djmail message was deleted (by `djmail_delete_old_messages`, say) keeps
its metadata; its djmail properties read empty and `status` is `None`. The link is
`on_delete=SET_NULL` rather than `PROTECT` so djmail's own cleanup keeps working, and so an
idempotency key keeps blocking a duplicate send after the message is gone.

## Recording metadata

Attach metadata to the `EmailMessage` before sending it. It travels as an attribute (never
a header) and is removed before djmail pickles the message:

```python
from django.core.mail import EmailMultiAlternatives

from baseapp.email_log.services import attach_log_metadata, get_email_log

email = EmailMultiAlternatives(subject, text, to=[customer.email], cc=[accounts_email])
email.attach_alternative(html, "text/html")
attach_log_metadata(
    email,
    template="invoices/paid",
    context={"invoice_number": invoice.number},
    related=invoice,
    category="billing",
    sent_by=request.user,
)
email.send()

log = get_email_log(email)  # the row written for it
```

`context` is stored as JSON; values JSON cannot hold (model instances, ...) are stored as
their `str()`. Keep secrets such as one-time tokens out of it, or purge rows regularly (see
below): the context is kept so the message can be re-rendered.

## Sending once: idempotency keys

```python
from baseapp.email_log.services import send_logged

log = send_logged(email, idempotency_key=f"invoice-{invoice.pk}-paid", related=invoice)
```

`send_logged` returns the existing row, and sends nothing, when the key is already logged.
Two concurrent calls with the same key are settled by the key's unique constraint: the
message and row are written atomically before anything is sent, so the loser's are rolled
back and it gets the winner's row. Keyword arguments other than `idempotency_key` and
`connection` are those of `attach_log_metadata`.

A key attached with `attach_log_metadata(email, idempotency_key=...)` is honoured by the
backends too: an email whose key is taken is not sent (`get_email_log(email)` is the
existing row).

`send_logged` logs whatever `EMAIL_BACKEND` is: with a non-logging backend (the test
runner's locmem backend, an SMTP backend) it sends through that backend as transport; with
plain djmail backends it uses their logging counterpart.

## Transport errors

djmail catches transport exceptions and stores the traceback in `Message.exception`, but
leaves the message a draft and does not count the attempt, so it is never retried. The
logging backends mark it `failed` and count the attempt instead: `log.status == "failed"`
and `log.error` holds the traceback. `send()` still returns `0` rather than raising, as
with djmail.

The same goes for a transport that cannot be reached at all (an SMTP server that is down
fails when the connection opens, before any message is handed to it, and djmail lets that
exception reach the caller): every message of the call is marked `failed` with the
connection error, and `send()` returns. With `CeleryEmailBackend`, the worker does the same,
and a broker that cannot take the task marks the queued messages `failed` instead of
raising after the caller's transaction committed. The retry task sends them all once the
transport is back.

`EmailBackend` sends inside the caller's transaction, as djmail's does: if the caller then
rolls back, the email is already out but its message, row and idempotency key are gone.
Send after the commit (`transaction.on_commit`) or use `CeleryEmailBackend`, which queues
delivery on commit, when that matters.

## Attachments

Every row lists its attachments as `{"name", "content_type", "size"}`. To also keep the
files outside djmail's pickled message:

```python
BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS = True
# A STORAGES alias, or the dotted path of a storage class or factory. Default: default_storage.
BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE = "private"
```

Each entry then has a `"path"` in that storage; `attachments.read_stored_attachment(entry)`
returns the content. Attachments are often invoices and other personal documents: use a
private storage. A file that fails to save is logged and described without a path; it never
stops the email.

## Resending

```python
from baseapp.email_log.services import resend

copy = resend(log, sent_by=request.user)  # copy.resend_of == log
```

`resend` sends a new djmail message with a new row, copying the template, context,
category and related object. By default it sends djmail's stored message again as it was.
To re-render from the template and stored context instead, configure a renderer:

```python
# (template, context) -> dict with any of "subject", "body_text", "body_html"
BASEAPP_EMAIL_LOG_RENDERER = "myproject.emails.render_logged_email"
```

Keys the renderer leaves out fall back to the original message. Recipients, cc, bcc and
reply-to come from the row; attachments from djmail's stored message, or, once that is gone,
from the attachment storage. `ResendError` is raised for rows of other channels and when
the djmail message is gone and there is no renderer.

The admin offers the same as a "Resend the selected emails" action.

## Other channels

Messages that do not go through djmail (SMS, push, ...) can share the log:

```python
from baseapp.email_log.services import log_channel_message

log = log_channel_message(
    channel="sms",
    to="+15555550100",
    body_text="Your code is 123456",
    category="auth",
    idempotency_key=f"login-code-{attempt.pk}",
)
deliver_sms(log.delivery_to, log.delivery_body_text)
log.mark_delivery("sent")  # or log.mark_delivery("failed", error="...")
```

## Retry and retention

Two Celery tasks, contributed to the plugin registry's beat schedules:

| Task | Default schedule | What it does |
|---|---|---|
| `baseapp.email_log.tasks.retry_failed_emails` | every 15 minutes | djmail's periodic pass: discard messages that failed more than `DJMAIL_MAX_RETRY_NUMBER` (default 3) times, then send pending low-priority messages and retry the other failed ones. Covers every djmail message, logged or not. It also sends logged messages still drafts `BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES` after they were written (a Celery task that was lost, a process that died before queueing it). |
| `baseapp.email_log.tasks.purge_email_logs` | daily | Delete rows older than `BASEAPP_EMAIL_LOG_RETENTION_DAYS` with their djmail messages and stored attachments, plus djmail messages that old with no row. No-op while the setting is `None` (the default). |

Each message is locked while it is delivered and skipped if it is no longer eligible, so a
retry run overlapping another run, or the Celery worker, never sends a message twice. A
message is attempted at most once per run: one that fails is retried by the next run.

The purge deletes every djmail message older than the retention, including messages sent
before the log was installed or through plain djmail, which have no row.

Rows with an idempotency key are kept by the purge, so their keys keep blocking duplicate
sends, unless `BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT = True`. `purge_email_logs(older_than_days=N)`
overrides the setting for one run.

Projects that build `CELERY_BEAT_SCHEDULE` from the registry get both:

```python
CELERY_BEAT_SCHEDULE = {
    ...,
    **plugin_registry.get_all_celery_schedules(),
}
```

Or add them by hand:

```python
CELERY_BEAT_SCHEDULE = {
    "retry_failed_emails": {
        "task": "baseapp.email_log.tasks.retry_failed_emails",
        "schedule": crontab(minute="*/15"),
    },
    "purge_email_logs": {
        "task": "baseapp.email_log.tasks.purge_email_logs",
        "schedule": crontab(hour=3, minute=30),
    },
}
BASEAPP_EMAIL_LOG_RETENTION_DAYS = 90
```

Schedule one retry task only: drop djmail's own `djmail.tasks.retry_send_messages` if the
project scheduled it, since it would leave transport errors uncounted.

## Settings

| Setting | Default | |
|---|---|---|
| `BASEAPP_EMAIL_LOG_EMAILLOG_MODEL` | `"baseapp_email_log.EmailLog"` | The swappable model (see below) |
| `BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS` | `False` | Save attachments to the storage below |
| `BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE` | `None` (`default_storage`) | `STORAGES` alias, or dotted path of a storage class or factory |
| `BASEAPP_EMAIL_LOG_RETENTION_DAYS` | `None` (keep) | Age in days after which `purge_email_logs` deletes rows |
| `BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT` | `False` | Let the purge delete rows holding an idempotency key |
| `BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES` | `30` | Age after which `retry_failed_emails` sends a logged message still a draft; `None` leaves drafts alone |
| `BASEAPP_EMAIL_LOG_RENDERER` | `None` | Callable or dotted path re-rendering a template on resend |
| `DJMAIL_REAL_BACKEND`, `DJMAIL_MAX_RETRY_NUMBER` | djmail's | Unchanged meaning |

## Customizing the model

The package ships a concrete `EmailLog` with its migration, so it works out of the box.
To add columns (an owner, a tenant, ...), subclass the abstract model and swap it in before
the first `migrate`:

```python
# myapp/models.py
from baseapp.email_log.models import AbstractEmailLog


class EmailLog(AbstractEmailLog):
    account = models.ForeignKey("accounts.Account", null=True, on_delete=models.CASCADE)

    class Meta(AbstractEmailLog.Meta):
        pass
```

```python
# settings.py
BASEAPP_EMAIL_LOG_EMAILLOG_MODEL = "myapp.EmailLog"
```

Package code always loads the active model with `get_email_log_model()`
(`swapper.load_model("baseapp_email_log", "EmailLog")`); do the same. To fill custom
columns, set them on `get_email_log(email)` after sending, or subclass the backend.

## Admin

`EmailLog` is registered read-only: djmail's fields (subject, from, to, status, sent date,
error, retries, bodies) are shown next to the log's own, HTML bodies as escaped source.
Filter by status, channel, category and date; search by subject, any recipient (To, cc,
bcc, channel address), related label or idempotency key.
