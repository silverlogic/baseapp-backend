from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .emails import send_password_expired_email

# ``app.autodiscover_tasks()`` only imports ``<app>.tasks`` for each installed app. The anonymize
# task is defined in ``baseapp_auth.rest_framework.users.tasks``, which nothing imports in the
# worker process, so re-export it here to make sure the worker registers it. The task keeps its
# original name (``baseapp_auth.rest_framework.users.tasks.anonymize_and_delete_user_task``), so
# messages already queued with an ETA are still picked up.
from .rest_framework.users.tasks import anonymize_and_delete_user_task

__all__ = ["anonymize_and_delete_user_task", "notify_users_is_password_expired"]

User = get_user_model()


@shared_task
def notify_users_is_password_expired() -> None:
    users = (
        User.objects.all()
        .add_is_password_expired()
        .filter(password_expiry_date__date=timezone.now())
    )
    for user in users:
        send_password_expired_email(user)
