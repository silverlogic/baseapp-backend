from typing import Optional, Protocol, runtime_checkable

from stevedore import named
from stevedore.exception import NoMatches


@runtime_checkable
class ServiceProvider(Protocol):
    @property
    def service_name(self) -> str:
        pass

    def is_available(self) -> bool:
        pass


class BaseAppServiceRegistry:
    NAMESPACE = "baseapp.services"

    def __init__(self):
        self._manager: Optional[named.NamedExtensionManager] = None
        self._initialized = False

    def _get_manager(self) -> named.NamedExtensionManager:
        if self._manager is None:
            try:
                self._manager = named.NamedExtensionManager(
                    namespace=self.NAMESPACE,
                    invoke_on_load=True,
                )
            except NoMatches:
                self._manager = named.NamedExtensionManager(
                    namespace=self.NAMESPACE,
                    invoke_on_load=True,
                    verify_requirements=False,
                )
        return self._manager

    def load_from_installed_apps(self):
        if self._initialized:
            return
        self._initialized = True

    def get_service(self, service_name: str) -> Optional[ServiceProvider]:
        if not self._initialized:
            self.load_from_installed_apps()

        manager = self._get_manager()

        if service_name not in manager:
            return None

        service = manager[service_name].obj

        if not isinstance(service, ServiceProvider):
            return None

        if not service.is_available():
            return None

        return service

    def has_service(self, service_name: str) -> bool:
        service = self.get_service(service_name)
        return service is not None


service_registry = BaseAppServiceRegistry()
