import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction

from baseapp_auth.anonymization import anonymize_activitylog
from baseapp_auth.emails import (
    send_anonymize_user_error_email,
    send_anonymize_user_success_email,
)
from baseapp_core.plugins import shared_services


@shared_task
def anonymize_and_delete_user_task(user_id):
    User = get_user_model()
    user = User.objects.get(id=user_id)
    user_email = user.email

    try:
        with transaction.atomic():
            anonymize_activitylog(user)

            if service := shared_services.get("chats_participation"):
                service.cleanup_user_participation(user)

            user.delete()
        send_anonymize_user_success_email(user_email)
    except Exception as e:
        logging.exception(e)
        send_anonymize_user_error_email(user_email)
        pass
