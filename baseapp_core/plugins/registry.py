from typing import Any, Dict, List, Optional, Tuple, Union

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.urls import include, path, re_path
from django.utils.module_loading import import_string
from stevedore import ExtensionManager
from stevedore.exception import NoMatches

from .base import BaseAppPlugin, PackageSettings, SlottedList


class PluginRegistry:
    NAMESPACE = "baseapp.plugins"

    def __init__(self) -> None:
        self._manager: Optional[ExtensionManager] = None
        self._plugins: Dict[str, BaseAppPlugin] = {}
        self._settings_cache: Dict[str, PackageSettings] = {}
        self._initialized = False

    def _get_manager(self) -> ExtensionManager:
        if self._manager is None:
            try:
                self._manager = ExtensionManager(
                    namespace=self.NAMESPACE,
                    invoke_on_load=True,
                )
            except NoMatches:
                self._manager = ExtensionManager(
                    namespace=self.NAMESPACE,
                    invoke_on_load=True,
                    verify_requirements=False,
                )
        return self._manager

    def _is_app_installed(self, package_name: str) -> bool:
        try:
            return apps.is_installed(package_name)
        except Exception:
            try:
                from django.conf import settings

                return package_name in settings.INSTALLED_APPS
            except Exception:
                return False

    def load_from_installed_apps(self) -> None:
        if self._initialized:
            return

        manager = self._get_manager()

        for extension in manager:
            plugin = extension.obj

            if not isinstance(plugin, BaseAppPlugin):
                raise ImproperlyConfigured(
                    f"Plugin '{extension.name}' does not implement BaseAppPlugin"
                )

            if not self._is_app_installed(plugin.package_name):
                continue

            errors = plugin.validate()
            if errors:
                raise ImproperlyConfigured(
                    f"Plugin '{plugin.name}' validation failed: {', '.join(errors)}"
                )

            self._plugins[plugin.name] = plugin
            self._settings_cache[plugin.name] = plugin.get_settings()

        self._initialized = True

    def get_plugin(self, name: str) -> Optional[BaseAppPlugin]:
        if not self._initialized:
            self.load_from_installed_apps()
        return self._plugins.get(name)

    def get_all_plugins(self) -> List[BaseAppPlugin]:
        if not self._initialized:
            self.load_from_installed_apps()
        return list(self._plugins.values())

    def _get_by_alias(self, settings: PackageSettings, key: str) -> Any:
        """Access PackageSettings by alias (e.g. INSTALLED_APPS) via model_dump(by_alias=True)."""
        data = settings.model_dump(by_alias=True)
        if key not in data:
            known = sorted(data.keys())
            raise KeyError(f"Unknown registry key: {key!r}. Known: {known}")
        return data[key]

    def _normalize_slotted(self, value: SlottedList) -> Tuple[List[str], Dict[str, List[str]]]:
        """Return (flat_list, slot_name -> list). SlottedList is Dict; empty dict = no slots."""
        if not value:
            return ([], {})
        return (sum(value.values(), []), value)

    def get(self, key: str, slot: Optional[str] = None) -> List[Any]:
        """
        Get aggregated list for a Django-style setting key (alias or field name).

        - get("INSTALLED_APPS") -> all plugins' installed_apps merged.
        - get("MIDDLEWARE") -> all middleware entries merged (flat).
        - get("MIDDLEWARE", "auth") -> only entries from plugins that registered
          under slot "auth". If a plugin is disabled, its contribution is omitted.
        """
        if not self._initialized:
            self.load_from_installed_apps()

        if key in PackageSettings.SLOTTED_KEYS:
            result: List[Any] = []
            for plugin in self._plugins.values():
                settings = self._settings_cache[plugin.name]
                value = self._get_by_alias(settings, key)
                flat, by_slot = self._normalize_slotted(value)
                if slot is None:
                    result.extend(flat)
                else:
                    result.extend(by_slot.get(slot, []))
            return result

        # Simple list aggregation
        result = []
        for plugin in self._plugins.values():
            settings = self._settings_cache[plugin.name]
            val = self._get_by_alias(settings, key)
            if isinstance(val, list):
                result.extend(val)
            else:
                result.append(val)
        return result

    def _collect_list_attr(self, key: str) -> List[Any]:
        if not self._initialized:
            self.load_from_installed_apps()
        result: List[Any] = []
        for plugin in self._plugins.values():
            settings = self._settings_cache[plugin.name]
            value = self._get_by_alias(settings, key)
            if isinstance(value, list):
                result.extend(value)
            elif isinstance(value, dict):
                result.extend(sum(value.values(), []))
            else:
                raise ImproperlyConfigured(f"Plugin '{plugin.name}' has an invalid {key} attribute")
        return result

    def _merge_dict_attr(self, key: str) -> Dict[Any, Any]:
        if not self._initialized:
            self.load_from_installed_apps()
        result: Dict[Any, Any] = {}
        for plugin in self._plugins.values():
            settings = self._settings_cache[plugin.name]
            value = self._get_by_alias(settings, key)
            if isinstance(value, dict):
                result.update(value)
            else:
                raise ImproperlyConfigured(f"Plugin '{plugin.name}' has an invalid {key} attribute")
        return result

    def _collect_classes_or_strings(self, classes_or_strings: List[Any]) -> List[Any]:
        classes = []
        for class_or_string in classes_or_strings:
            if isinstance(class_or_string, str):
                classes.append(import_string(class_or_string))
            else:
                classes.append(class_or_string)
        return classes

    def _resolve_urlpatterns(self, urlpatterns: List[Any]) -> List[Union[path, re_path]]:
        result: List[Any] = []
        for urlpattern in urlpatterns:
            if callable(urlpattern):
                resolved = urlpattern(include, path, re_path)
                if isinstance(resolved, list):
                    result.extend(resolved)
                else:
                    result.append(resolved)
            else:
                result.append(urlpattern)
        return result

    # --- Convenience get_all_* (delegate to get() where possible) ---

    def get_all_installed_apps(self) -> List[str]:
        return self.get("INSTALLED_APPS")

    def get_all_middleware(self) -> List[str]:
        return self.get("MIDDLEWARE")

    def get_all_auth_backends(self) -> List[str]:
        return self.get("AUTHENTICATION_BACKENDS")

    def get_all_graphene_middleware(self) -> List[str]:
        return self.get("GRAPHENE__MIDDLEWARE")

    def get_all_django_extra_settings(self) -> Dict[str, Any]:
        return self._merge_dict_attr("django_extra_settings")

    def get_all_celery_schedules(self) -> Dict[str, Any]:
        return self._merge_dict_attr("celery_beat_schedules")

    def get_all_constance_config(self) -> List[Tuple[str, tuple]]:
        constance_config = self._merge_dict_attr("constance_config")
        return list(constance_config.items())

    def get_all_urlpatterns(self) -> List[Any]:
        """
        Return URL patterns from all plugins.
        Each plugin should define a function that returns a list of path or re_path objects.
        Example:
        def urlpatterns(include, path, re_path):
            return [
                re_path(r"", include("baseapp_auth.urls")),
            ]
        """
        urlpatterns = self.get("urlpatterns")
        return self._resolve_urlpatterns(urlpatterns)

    def get_all_v1_urlpatterns(self) -> List[Any]:
        """
        Return URL patterns from all plugins.
        Each plugin should define a function that returns a list of path or re_path objects.
        Example:
        def v1_urlpatterns(include, path, re_path):
            return [
                re_path(r"", include("baseapp_auth.urls")),
            ]
        """
        urlpatterns = self.get("v1_urlpatterns")
        return self._resolve_urlpatterns(urlpatterns)

    def get_all_graphql_queries(self) -> List[Any]:
        queries_classes_or_strings = self.get("graphql_queries")
        return self._collect_classes_or_strings(queries_classes_or_strings)

    def get_all_graphql_mutations(self) -> List[Any]:
        mutations_classes_or_strings = self.get("graphql_mutations")
        return self._collect_classes_or_strings(mutations_classes_or_strings)

    def get_all_graphql_subscriptions(self) -> List[Any]:
        subscriptions_classes_or_strings = self.get("graphql_subscriptions")
        return self._collect_classes_or_strings(subscriptions_classes_or_strings)


plugin_registry = PluginRegistry()
