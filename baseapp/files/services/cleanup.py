import logging
from datetime import timedelta

import swapper
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from ..storage import get_files_storage, get_upload_handler

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_uploads():
    """
    Celery task to cleanup expired/abandoned uploads.

    Run this periodically (e.g., hourly via celery beat).
    """
    # Loaded lazily (not at import time): this module is imported during Celery
    # startup, which can precede Django's app registry being ready.
    File = swapper.load_model("baseapp_files", "File")
    handler = get_upload_handler()
    now = timezone.now()

    # Find expired uploads
    expired_files = File.objects.filter(
        upload_status__in=[File.UploadStatus.PENDING, File.UploadStatus.UPLOADING],
        upload_expires_at__lt=now,
    )

    cleaned_count = 0
    for file_obj in expired_files:
        try:
            if file_obj.upload_id:
                handler.abort_upload(file_obj, file_obj.upload_id)

            file_obj.upload_status = File.UploadStatus.ABORTED
            file_obj.upload_id = ""
            file_obj.save()

            cleaned_count += 1
        except Exception:
            # Log with traceback but continue with the next file.
            logger.exception("Failed to cleanup file %s", file_obj.id)

    logger.info(f"Cleaned up {cleaned_count} expired uploads")
    return f"Cleaned up {cleaned_count} expired uploads"


@shared_task
def cleanup_unclaimed_anonymous_files() -> str:
    """
    Delete anonymous uploads never attached to anything, with their stored object, once
    older than ``BASEAPP_FILES_UNCLAIMED_ANONYMOUS_MAX_AGE`` seconds.

    Only files that came through the upload API (``total_parts`` set) without a creator
    qualify, so files a project creates itself without a user are never touched. Does
    nothing while ``BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS`` is off.
    """
    from ..permissions import anonymous_uploads_allowed

    if not anonymous_uploads_allowed():
        return "Anonymous uploads are disabled"

    File = swapper.load_model("baseapp_files", "File")
    handler = get_upload_handler()
    storage = get_files_storage()
    max_age = getattr(settings, "BASEAPP_FILES_UNCLAIMED_ANONYMOUS_MAX_AGE", 24 * 60 * 60)
    cutoff = timezone.now() - timedelta(seconds=max_age)

    unclaimed = File.objects.filter(
        created_by__isnull=True,
        parent__isnull=True,
        total_parts__isnull=False,
        created__lt=cutoff,
    )

    deleted_count = 0
    for file_obj in unclaimed:
        try:
            if file_obj.upload_id:
                handler.abort_upload(file_obj, file_obj.upload_id)
            if file_obj.file:
                storage.delete(file_obj.file.name)
            file_obj.delete()
            deleted_count += 1
        except Exception:
            logger.exception("Failed to delete unclaimed anonymous file %s", file_obj.id)

    logger.info("Deleted %s unclaimed anonymous files", deleted_count)
    return f"Deleted {deleted_count} unclaimed anonymous files"


def cleanup_failed_uploads(days_old=7):
    """
    Cleanup failed/aborted uploads older than specified days.

    Can be called manually or via management command.
    """
    File = swapper.load_model("baseapp_files", "File")
    cutoff = timezone.now() - timedelta(days=days_old)

    deleted_count, _ = File.objects.filter(
        upload_status__in=[File.UploadStatus.FAILED, File.UploadStatus.ABORTED],
        modified__lt=cutoff,
    ).delete()

    logger.info(f"Deleted {deleted_count} old failed/aborted uploads")
    return f"Deleted {deleted_count} old failed/aborted uploads"
