from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PackageSettings:
    installed_apps: List[str] = field(default_factory=list)
    middleware: List[str] = field(default_factory=list)
    authentication_backends: List[str] = field(default_factory=list)
    graphql_middleware: List[str] = field(default_factory=list)
    env_vars: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    django_settings: Dict[str, Any] = field(default_factory=dict)
    celery_beat_schedules: Dict[str, Any] = field(default_factory=dict)
    celery_task_routes: Dict[str, Any] = field(default_factory=dict)
    constance_config: Dict[str, tuple] = field(default_factory=dict)

    urlpatterns: List[Any] = field(default_factory=list)
    graphql_queries: List[Any] = field(default_factory=list)
    graphql_mutations: List[Any] = field(default_factory=list)
    graphql_subscriptions: List[Any] = field(default_factory=list)

    required_packages: List[str] = field(default_factory=list)
    optional_packages: List[str] = field(default_factory=list)


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
