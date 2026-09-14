from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class MessageTemplatesPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_message_templates"

    @property
    def package_name(self) -> str:
        return "baseapp_message_templates"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=[],
            optional_packages=[],
        )
