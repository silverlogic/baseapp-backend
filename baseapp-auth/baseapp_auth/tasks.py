from django.utils import timezone

from celery import shared_task

from .emails import send_password_expired_email
from .models import User


@shared_task
def notify_users_is_password_expired():
    users = User.objects.all().filter(password_expiry_date__date=timezone.now())
    for user in users:
        send_password_expired_email(user)
