"""
Attachments of logged emails.

djmail keeps attachments inside its pickled message, which only djmail can read. The log
describes each one (name, content type, size) and, when
``BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS`` is on, also saves the file to
``BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE`` and records its path, so it can be listed,
downloaded or re-attached without unpickling anything.

``read_attachment`` reads an attachment from wherever it still is: djmail's pickled message
first, then the storage.
"""

import logging
import uuid
from email.mime.base import MIMEBase
from typing import TYPE_CHECKING, Any, Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage, storages
from django.core.mail import EmailMessage
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.text import get_valid_filename

if TYPE_CHECKING:
    from .models import AbstractEmailLog

logger = logging.getLogger(__name__)

ATTACHMENTS_FOLDER = "email_log"


def get_attachment_storage() -> Storage:
    """
    The storage holding stored attachments: ``BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE`` is a
    ``STORAGES`` alias, or the dotted path of a storage class or of a callable returning a
    storage. ``None`` (the default) is ``default_storage``.
    """
    value = getattr(settings, "BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE", None)
    if not value:
        return default_storage
    if value in settings.STORAGES:
        return storages[value]
    return import_string(value)()


def _read_attachment(attachment: Any) -> tuple[str, bytes, str]:
    """``(filename, content, mimetype)`` of a MIME part or an ``(filename, content, mimetype)`` tuple."""
    if isinstance(attachment, MIMEBase):
        content = attachment.get_payload(decode=True) or b""
        return attachment.get_filename() or "", content, attachment.get_content_type()
    filename, content, mimetype = attachment
    if isinstance(content, str):
        content = content.encode(settings.DEFAULT_CHARSET)
    return filename or "", content or b"", mimetype or "application/octet-stream"


def _store(storage: Storage, filename: str, content: bytes) -> str:
    name = get_valid_filename(filename) or "attachment"
    path = f"{ATTACHMENTS_FOLDER}/{timezone.now():%Y/%m/%d}/{uuid.uuid4().hex}/{name}"
    return storage.save(path, ContentFile(content))


def describe_attachments(email: EmailMessage, *, store: Optional[bool] = None) -> list[dict]:
    """
    One ``{"name", "content_type", "size"}`` entry per attachment, plus ``"path"`` when the
    file was saved to the attachment storage. A file that fails to save is logged and
    described without a path: storage trouble never stops an email.
    """
    if store is None:
        store = getattr(settings, "BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS", False)
    storage = get_attachment_storage() if store else None

    described = []
    for attachment in getattr(email, "attachments", None) or []:
        filename, content, mimetype = _read_attachment(attachment)
        entry = {"name": filename, "content_type": mimetype, "size": len(content)}
        if storage is not None:
            try:
                entry["path"] = _store(storage, filename, content)
            except Exception:
                logger.exception("Could not store the email attachment %r", filename)
        described.append(entry)
    return described


def read_stored_attachment(entry: dict) -> Optional[bytes]:
    """The content of a stored attachment, or ``None`` when it was not stored."""
    path = entry.get("path")
    if not path:
        return None
    with get_attachment_storage().open(path, "rb") as stored:
        return stored.read()


def read_attachment(log: "AbstractEmailLog", index: int) -> Optional[tuple[str, bytes, str]]:
    """
    ``(filename, content, content_type)`` of the attachment at ``index`` of ``log`` (the
    order of ``log.attachments``), read from djmail's pickled message when it is still
    there, otherwise from the attachment storage. ``None`` when neither holds it: the index
    is out of range, the djmail message is gone and the file was not stored, or the stored
    file is missing.
    """
    if index < 0:
        return None
    original = log.get_email_message()
    if original is not None and index < len(original.attachments):
        filename, content, content_type = _read_attachment(original.attachments[index])
        entries = log.attachments or []
        if not filename and index < len(entries):
            filename = entries[index].get("name") or ""
        return filename, content, content_type

    entries = log.attachments or []
    if index >= len(entries):
        return None
    entry = entries[index]
    try:
        content = read_stored_attachment(entry)
    except Exception:
        # A missing file, or any error of a remote storage: report it as unreadable.
        logger.exception("Could not read the stored email attachment %s", entry.get("path"))
        return None
    if content is None:
        return None
    return (
        entry.get("name") or "",
        content,
        entry.get("content_type") or "application/octet-stream",
    )


def delete_stored_attachments(entries: list[dict]) -> None:
    """Delete the stored files of ``entries``; missing files are ignored."""
    storage = None
    for entry in entries or []:
        path = entry.get("path")
        if not path:
            continue
        storage = storage or get_attachment_storage()
        try:
            storage.delete(path)
        except Exception:
            logger.exception("Could not delete the stored email attachment %s", path)
