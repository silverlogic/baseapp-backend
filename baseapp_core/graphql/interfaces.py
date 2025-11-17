from typing import Any, List, Optional

from stevedore import extension
from stevedore.exception import NoMatches


class BaseAppInterfaceRegistry:
    NAMESPACE = "baseapp.interfaces"

    def __init__(self):
        self._manager: Optional[extension.ExtensionManager] = None
        self._initialized = False

    def _get_manager(self) -> extension.ExtensionManager:
        if self._manager is None:
            try:
                self._manager = extension.ExtensionManager(
                    namespace=self.NAMESPACE,
                    invoke_on_load=True,
                )
            except NoMatches:
                self._manager = extension.ExtensionManager(
                    namespace=self.NAMESPACE,
                    invoke_on_load=True,
                    verify_requirements=False,
                )
        return self._manager

    def load_from_installed_apps(self):
        if self._initialized:
            return
        self._initialized = True

    def get_all_interfaces(self) -> List[Any]:
        if not self._initialized:
            self.load_from_installed_apps()

        manager = self._get_manager()
        return [ext.obj for ext in manager if ext.obj]

    def get_interface(self, name: str) -> Optional[Any]:
        if not self._initialized:
            self.load_from_installed_apps()

        try:
            manager = self._get_manager()
            for ext in manager:
                if ext.name == name:
                    return ext.obj
        except Exception:
            pass
        return None

    def get_interfaces(
        self, interface_names: List[str], default_interfaces: List[Any] = None
    ) -> tuple:
        if default_interfaces is None:
            default_interfaces = []

        interfaces = list(default_interfaces)

        for name in interface_names:
            interface = self.get_interface(name)
            if interface:
                interfaces.append(interface)

        return tuple(interfaces)


interface_registry = BaseAppInterfaceRegistry()
