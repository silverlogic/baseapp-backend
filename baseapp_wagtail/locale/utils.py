import re

from wagtail.models import Locale


def clear_pathname(pathname: str) -> str:
    locales = Locale.objects.values_list("language_code", flat=True)
    locale_pattern = re.compile(r"^/({})(/|$)".format("|".join(locales)))
    return re.sub(locale_pattern, "/", pathname)
