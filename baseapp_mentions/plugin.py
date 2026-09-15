from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class MentionsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_mentions"

    @property
    def package_name(self) -> str:
        return "baseapp_mentions"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            required_packages=[
                {
                    "baseapp_profiles": "Mention targets a Profile via FK; this app relies on baseapp_profiles' Profile model."
                },
            ],
            optional_packages=[],
        )
