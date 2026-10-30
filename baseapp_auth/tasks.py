from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .emails import send_password_expired_email

# Celery's ``autodiscover_tasks()`` imports only ``<app>.tasks``, so the worker never sees
# modules like ``rest_framework.users.tasks`` on its own. Re-export the tasks defined there
# so the worker registers them; the task names are unchanged.
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
