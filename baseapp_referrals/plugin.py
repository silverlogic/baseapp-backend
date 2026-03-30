from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ReferralsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_referrals"

    @property
    def package_name(self) -> str:
        return "baseapp_referrals"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=[],
            optional_packages=[],
        )
