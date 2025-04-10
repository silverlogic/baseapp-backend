from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import SocialAuthAccessTokenCache


@shared_task
def clean_up_social_auth_cache():
    SocialAuthAccessTokenCache.objects.filter(
        created__lte=timezone.now() - timedelta(hours=1)
    ).delete()
