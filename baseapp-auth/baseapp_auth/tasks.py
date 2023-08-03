from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .emails import send_password_expired_email

User = get_user_model()


@shared_task
def notify_users_is_password_expired():
    users = User.objects.all().filter(password_expiry_date__date=timezone.now())
    for user in users:
        send_password_expired_email(user)
