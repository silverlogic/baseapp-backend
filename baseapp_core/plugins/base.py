from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Dict, List, Union

from django.urls import include, path, re_path
from pydantic import BaseModel, ConfigDict, Field

# For settings where order matters (e.g. MIDDLEWARE), plugins contribute a dict of slot_name -> list.
SlottedList = Dict[str, List[str]]


class PackageSettings(BaseModel):
    """
    Plugin-contributed settings. Keys match Django setting names via alias.

    - List fields (INSTALLED_APPS): flat list per plugin, merged.
    - Slotted fields: dict of slot_name -> list; use get(key, slot) in settings.
    - Dict fields (django_extra_settings, etc.): merged; last plugin wins on key conflict.
    """

    model_config = ConfigDict(populate_by_name=True)

    # Keys that support get(key, slot) for ordered retrieval. Add here when adding new slotted fields.
    SLOTTED_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "MIDDLEWARE",
            "AUTHENTICATION_BACKENDS",
            "GRAPHENE__MIDDLEWARE",
        }
    )

    # --- Django list settings (aggregated) ---
    installed_apps: List[str] = Field(default_factory=list, alias="INSTALLED_APPS")

    # --- Slotted list settings (order matters; use get(key, slot) in settings) ---
    authentication_backends: SlottedList = Field(
        default_factory=dict, alias="AUTHENTICATION_BACKENDS"
    )
    middleware: SlottedList = Field(default_factory=dict, alias="MIDDLEWARE")
    graphene_middleware: SlottedList = Field(default_factory=dict, alias="GRAPHENE__MIDDLEWARE")

    # --- Dict settings (merged) ---
    django_extra_settings: Dict[str, Any] = Field(default_factory=dict)
    celery_beat_schedules: Dict[str, Any] = Field(default_factory=dict)
    celery_task_routes: Dict[str, Any] = Field(default_factory=dict)
    constance_config: Dict[str, tuple] = Field(default_factory=dict)

    # --- GraphQL / URL (list, no slots by default) ---
    urlpatterns: Callable[[include, path, re_path], List[Union[path, re_path]]] = Field(
        default_factory=lambda: []
    )
    v1_urlpatterns: Callable[[include, path, re_path], List[Union[path, re_path]]] = Field(
        default_factory=lambda: []
    )
    graphql_queries: List[Any] = Field(default_factory=list)
    graphql_mutations: List[Any] = Field(default_factory=list)
    graphql_subscriptions: List[Any] = Field(default_factory=list)

    # --- Plugin deps ---
    required_packages: List[str] = Field(default_factory=list)
    optional_packages: List[str] = Field(default_factory=list)


class BaseAppPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def package_name(self) -> str:
        pass

    @abstractmethod
    def get_settings(self) -> PackageSettings:
        pass

    def validate(self) -> List[str]:
        errors = []
        from django.apps import apps
        from django.core.exceptions import AppRegistryNotReady

        settings = self.get_settings()

        for req_pkg in settings.required_packages:
            try:
                if not apps.is_installed(req_pkg):
                    errors.append(
                        f"Plugin '{self.name}' requires package '{req_pkg}' "
                        f"but it's not in INSTALLED_APPS"
                    )
            except AppRegistryNotReady:
                try:
                    from django.conf import settings as django_settings

                    if req_pkg not in django_settings.INSTALLED_APPS:
                        errors.append(
                            f"Plugin '{self.name}' requires package '{req_pkg}' "
                            f"but it's not in INSTALLED_APPS"
                        )
                except Exception:
                    pass

        return errors

    def ready(self):
        pass
