from typing import Any, Dict

from django.conf import settings
from django.test.signals import setting_changed
from rest_framework.settings import APISettings as _APISettings

SETTING_KEY = "E2E"

USER_SETTINGS = getattr(settings, SETTING_KEY, None)

DEFAULTS = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "testproject.e2e.scripts",
}

IMPORT_STRINGS = ()


class E2ESettings(_APISettings):  # pragma: no cover
    def __check_user_settings(self, user_settings: Dict[str, Any]) -> Dict[str, Any]:
        return user_settings


settings = E2ESettings(USER_SETTINGS, DEFAULTS, IMPORT_STRINGS)


def reload_api_settings(*args, **kwargs) -> None:  # pragma: no cover
    global settings

    setting, value = kwargs["setting"], kwargs["value"]

    if setting == SETTING_KEY:
        settings = E2ESettings(value, DEFAULTS, IMPORT_STRINGS)


setting_changed.connect(reload_api_settings)
