from celery import shared_task
from django.contrib.auth import get_user_model

from baseapp_auth.anonymization import anonymize_activitylog
from baseapp_auth.emails import (
    send_anonymize_user_error_email,
    send_anonymize_user_success_email,
)


@shared_task
def anonymize_user_task(user_id):
    User = get_user_model()
    user = User.objects.get(id=user_id)
    user_email = user.email

    try:
        anonymize_activitylog(user)
        user.delete()
        send_anonymize_user_success_email(user_email)
    except Exception:
        send_anonymize_user_error_email(user.id)
        pass
