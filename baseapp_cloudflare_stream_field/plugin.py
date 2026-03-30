from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class CloudflareStreamFieldPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_cloudflare_stream_field"

    @property
    def package_name(self) -> str:
        return "baseapp_cloudflare_stream_field"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=[],
            optional_packages=[],
        )
