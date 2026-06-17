from __future__ import annotations

import swapper
from django.apps import apps
from django.db import models

from baseapp_core.plugins import SharedServiceProvider


class BaseProfilesService(SharedServiceProvider):
    def is_available(self) -> bool:
        return apps.is_installed("baseapp_profiles")

    def _get_profile_model(self) -> type[models.Model]:
        return swapper.load_model("baseapp_profiles", "Profile")
