from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class PDFPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_pdf"

    @property
    def package_name(self) -> str:
        return "baseapp_pdf"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=[],
            optional_packages=[],
        )
