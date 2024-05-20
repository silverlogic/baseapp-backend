import logging

from django.conf import settings
from django.utils.safestring import mark_safe

from .models import ShortUrl

logger = logging.getLogger(__name__)


def shorten_url(full_url):
    try:
        short_url_path = ShortUrl.objects.create(full_url=full_url).public_short_url

        return mark_safe(f"{settings.FRONT_URL}{short_url_path}")
    except Exception as e:
        logger.exception(e)
        # if link shortening fails, just send the full link
        return full_url
