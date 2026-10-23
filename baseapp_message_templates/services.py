import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from .registry import preview_email_template
from .utils import attach_files

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

    from .models import EmailTemplate

DEFAULT_TEST_SEND_LIMIT = "10/h"
_PERIODS = {"s": 1, "m": 60, "h": 60 * 60, "d": 24 * 60 * 60}


class PreviewError(Exception):
    """The template could not be rendered with its sample values."""


class RateLimitExceeded(Exception):
    """The user sent more test emails than ``BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT`` allows."""


def parse_rate(rate: str | None) -> tuple[int, int] | None:
    """Parse ``"10/h"`` (or ``"10/hour"``, ``s``/``m``/``h``/``d``) into ``(count, seconds)``.

    ``None`` or ``""`` means no limit.
    """
    if not rate:
        return None
    count, _sep, period = str(rate).partition("/")
    try:
        return int(count), _PERIODS[period.strip()[0].lower()]
    except (ValueError, KeyError, IndexError):
        raise ValueError(f"Invalid rate {rate!r}; use '<count>/<s|m|h|d>', e.g. '10/h'.")


def consume_test_send_quota(user: "AbstractBaseUser") -> bool:
    """Count one test send for ``user``; return ``False`` when the limit is already reached.

    A fixed window per user, kept in the default cache.
    """
    rate = parse_rate(
        getattr(settings, "BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT", DEFAULT_TEST_SEND_LIMIT)
    )
    if rate is None:
        return True
    limit, period = rate
    key = f"baseapp_message_templates:test_send:{user.pk}"
    if cache.add(key, 1, timeout=period):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # expired between add() and incr()
            cache.set(key, 1, timeout=period)
            count = 1
    return count <= limit


def with_unsaved_text(
    template: "EmailTemplate", overrides: Mapping[str, str | None] | None
) -> tuple["EmailTemplate", dict[str, str]]:
    """Apply an editor's unsaved text to an in-memory copy of ``template``.

    Returns the copy and the non-blank overrides. A blank value blanks that part on the copy,
    so it renders its default instead of the saved override, as it will once saved. ``None``
    keeps the saved text. Nothing is written to the database.
    """
    row = copy.copy(template)
    non_blank: dict[str, str] = {}
    for part, text in (overrides or {}).items():
        if text is None:
            continue
        if text.strip():
            non_blank[part] = text
        else:
            setattr(row, part, "")
    return row, non_blank


def build_test_email(
    template: "EmailTemplate",
    user: "AbstractBaseUser",
    overrides: Mapping[str, str | None] | None = None,
) -> EmailMultiAlternatives:
    """The test email of ``template`` for ``user``: sample values, ``[Test]`` subject prefix.

    ``overrides`` is unsaved text, applied as in :func:`with_unsaved_text`. Raises
    :class:`PreviewError` when rendering fails.
    """
    row, overrides = with_unsaved_text(template, overrides)
    try:
        preview = preview_email_template(template.name, overrides, recipient=user.email, row=row)
    except Exception as exc:
        raise PreviewError(str(exc)) from exc
    email = EmailMultiAlternatives(
        subject=f"{_('[Test]')} {preview.subject}",
        body=preview.body_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    if preview.body_html:
        email.attach_alternative(preview.body_html, "text/html")
    if template.pk:
        attach_files(email, list(template.static_attachments.all()))
    return email


def send_test_email(
    template: "EmailTemplate",
    user: "AbstractBaseUser",
    overrides: Mapping[str, str | None] | None = None,
) -> str:
    """Send a test of ``template`` to ``user``'s own address and return that address.

    The email is rendered with sample values (unsaved ``overrides`` included) and delivered by
    ``BASEAPP_MESSAGE_TEMPLATES_TEST_SENDER`` (a dotted ``callable(email_message, *, template,
    user)``; ``template`` is the template name) or, when unset, ``email_message.send()``.

    Raises:
        RateLimitExceeded: When ``BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT`` is reached.
        PreviewError: When the template cannot render with its sample values.
    """
    email = build_test_email(template, user, overrides)
    if not consume_test_send_quota(user):
        raise RateLimitExceeded()
    sender: Any = getattr(settings, "BASEAPP_MESSAGE_TEMPLATES_TEST_SENDER", None)
    if sender:
        sender = import_string(sender) if isinstance(sender, str) else sender
        sender(email, template=template.name, user=user)
    else:
        email.send()
    return user.email
