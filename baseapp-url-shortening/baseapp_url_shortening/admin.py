import urllib.parse

from django.conf import settings
from django.contrib import admin

from baseapp_url_shortening.models import ShortUrl


@admin.register(ShortUrl)
class ShortUrlAdmin(admin.ModelAdmin):
    list_display = ("id", "short_code", "full_url", "shortened_url")

    def shortened_url(self, instance: ShortUrl) -> str | None:
        if front_url := getattr(settings, "FRONT_URL", None):
            return urllib.parse.urljoin(front_url, instance.public_short_url)
        return None
