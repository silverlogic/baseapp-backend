from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class OrganizationsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_organizations"

    @property
    def package_name(self) -> str:
        return "baseapp_organizations"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=[
                "baseapp_profiles",
            ],
        )
