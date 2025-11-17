from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class PagesPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_pages"

    @property
    def package_name(self) -> str:
        return "baseapp_pages"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            installed_apps=[
                "baseapp_pages",
            ],
            middleware=[],
            authentication_backends=[],
            env_vars={},
            django_settings={},
            required_packages=[
                "baseapp_core",
            ],
            optional_packages=[
                "baseapp_comments",
            ],
        )
