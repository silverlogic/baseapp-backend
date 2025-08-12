from celery import shared_task
from django.contrib.auth import get_user_model

@shared_task
def anonymize_user_task(user_id):
    User = get_user_model()
    user = User.objects.get(id=user_id)
    user.anonymize() 