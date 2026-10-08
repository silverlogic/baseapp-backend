import logging
from datetime import timedelta

import swapper
from celery import shared_task
from django.utils import timezone

from ..storage import get_upload_handler

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
