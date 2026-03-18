from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ChatsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_chats"

    @property
    def package_name(self) -> str:
        return "baseapp_chats"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=[
                "baseapp_profiles",
            ],
        )
