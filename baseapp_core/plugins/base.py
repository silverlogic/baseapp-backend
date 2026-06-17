from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Dict, List, Optional, Union

from django.urls import include, path, re_path
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    required_packages: List["PackageDependency"] = Field(default_factory=list)
    optional_packages: List["PackageDependency"] = Field(default_factory=list)

    @field_validator("required_packages", "optional_packages", mode="before")
    @classmethod
    def _normalize_package_dependencies(cls, value: Any) -> List["PackageDependency"]:
        """
        Normalize dependency entries into PackageDependency instances.

        Supported formats:
        - "baseapp_core"
        - {"baseapp_core": "Used for shared models and signals"}
        """
        if value is None:
            return []

        if not isinstance(value, list):
            raise ValueError("Dependencies must be a list")

        return [PackageDependency.from_value(item) for item in value]


class PackageDependency(BaseModel):
    package: str
    description: Optional[str] = None

    @classmethod
    def from_value(cls, value: Any) -> "PackageDependency":
        """
        Build a dependency from either a package string or a dict with one entry.
        """
        if isinstance(value, cls):
            return value

        if isinstance(value, str):
            return cls(package=value)

        if isinstance(value, dict):
            if len(value) != 1:
                raise ValueError(
                    "Dependency dict format must contain a single entry: {'package_name': 'description'}"
                )

            package, description = next(iter(value.items()))
            if not isinstance(package, str):
                raise ValueError("Dependency package name must be a string")
            if description is not None and not isinstance(description, str):
                raise ValueError("Dependency description must be a string or null")

            return cls(package=package, description=description)

        raise ValueError(
            "Dependency must be either a package string or a dict {'package_name': 'description'}"
        )


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

    def validate(self, installed_apps: List[str] = None) -> List[str]:
        errors = []
        settings = self.get_settings()
        for req_dep in settings.required_packages:
            req_pkg = req_dep.package
            message = f"Plugin '{self.name}' requires package '{req_pkg}'"
            if req_dep.description:
                message = f"{message} (used for: {req_dep.description})"
            message = f"{message} but it's not in INSTALLED_APPS"
            if not self._is_app_installed(req_pkg, installed_apps):
                errors.append(message)

        return errors

    def _is_app_installed(self, package_name: str, installed_apps: List[str] = None) -> bool:
        if installed_apps is not None:
            return package_name in installed_apps

        from django.apps import apps

        return apps.is_installed(package_name)

    def ready(self):
        pass
