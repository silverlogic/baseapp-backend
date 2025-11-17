import logging
from typing import Callable, Dict

from stevedore import hook
from stevedore.exception import NoMatches

logger = logging.getLogger(__name__)


class BaseAppHookManager:
    NAMESPACE = "baseapp.hooks"

    def __init__(self):
        self._managers: Dict[str, hook.HookManager] = {}

    def _get_manager(self, hook_name: str) -> hook.HookManager:
        if hook_name not in self._managers:
            try:
                self._managers[hook_name] = hook.HookManager(
                    namespace=self.NAMESPACE,
                    name=hook_name,
                    invoke_on_load=False,
                )
            except NoMatches:
                self._managers[hook_name] = hook.HookManager(
                    namespace=self.NAMESPACE,
                    name=hook_name,
                    invoke_on_load=False,
                    verify_requirements=False,
                )
        return self._managers[hook_name]

    def register(self, hook_name: str, handler: Callable):
        pass

    def emit(self, hook_name: str, *args, **kwargs):
        manager = self._get_manager(hook_name)

        for extension in manager:
            try:
                extension.obj(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Error in hook handler '{extension.name}' for '{hook_name}': {e}",
                    exc_info=True,
                )


hook_manager = BaseAppHookManager()
