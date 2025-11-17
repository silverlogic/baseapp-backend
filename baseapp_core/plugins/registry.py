from typing import Any, Dict, List, Optional, Tuple

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from stevedore import ExtensionManager
from stevedore.exception import NoMatches

from .base import BaseAppPlugin, PackageSettings


class PluginRegistry:
    NAMESPACE = "baseapp.plugins"

    def __init__(self):
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

    def load_from_installed_apps(self):
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

    def _collect_list_attr(self, attr: str) -> List[Any]:
        if not self._initialized:
            self.load_from_installed_apps()
        result = []
        for plugin in self._plugins.values():
            settings = self._settings_cache[plugin.name]
            value = getattr(settings, attr)
            if isinstance(value, list):
                result.extend(value)
            else:
                raise ImproperlyConfigured(
                    f"Plugin '{plugin.name}' has an invalid {attr} attribute"
                )
        return result

    def _merge_dict_attr(self, attr: str) -> Dict[Any, Any]:
        if not self._initialized:
            self.load_from_installed_apps()
        result = {}
        for plugin in self._plugins.values():
            settings = self._settings_cache[plugin.name]
            value = getattr(settings, attr)
            if isinstance(value, dict):
                result.update(value)
            else:
                raise ImproperlyConfigured(
                    f"Plugin '{plugin.name}' has an invalid {attr} attribute"
                )
        return result

    def _collect_classes_or_strings(self, classes_or_strings: List[Any]) -> List[Any]:
        classes = []
        for class_or_string in classes_or_strings:
            if isinstance(class_or_string, str):
                classes.append(import_string(class_or_string))
            else:
                classes.append(class_or_string)
        return classes

    def get_all_installed_apps(self) -> List[str]:
        return self._collect_list_attr("installed_apps")

    def get_all_middleware(self) -> List[str]:
        return self._collect_list_attr("middleware")

    def get_all_auth_backends(self) -> List[str]:
        return self._collect_list_attr("authentication_backends")

    def get_all_graphql_middleware(self) -> List[str]:
        return self._collect_list_attr("graphql_middleware")

    def get_all_django_settings(self) -> Dict[str, Any]:
        return self._merge_dict_attr("django_settings")

    def get_all_celery_schedules(self) -> Dict[str, Any]:
        return self._merge_dict_attr("celery_beat_schedules")

    def get_all_env_vars(self) -> Dict[str, Dict[str, Any]]:
        return self._merge_dict_attr("env_vars")

    def get_all_constance_config(self) -> List[Tuple[str, tuple]]:
        constance_config = self._merge_dict_attr("constance_config")
        return list(constance_config.items())

    def get_all_urlpatterns(self) -> List[Any]:
        return self._collect_list_attr("urlpatterns")

    def get_all_graphql_queries(self) -> List[Any]:
        queries_classes_or_strings = self._collect_list_attr("graphql_queries")
        return self._collect_classes_or_strings(queries_classes_or_strings)

    def get_all_graphql_mutations(self) -> List[Any]:
        mutations_classes_or_strings = self._collect_list_attr("graphql_mutations")
        return self._collect_classes_or_strings(mutations_classes_or_strings)

    def get_all_graphql_subscriptions(self) -> List[Any]:
        subscriptions_classes_or_strings = self._collect_list_attr("graphql_subscriptions")
        return self._collect_classes_or_strings(subscriptions_classes_or_strings)


plugin_registry = PluginRegistry()
