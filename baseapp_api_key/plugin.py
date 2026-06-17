from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ApiKeyPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_api_key"

    @property
    def package_name(self) -> str:
        return "baseapp_api_key"

    def get_settings(self) -> PackageSettings:
        from baseapp_core.settings.env import env

        return PackageSettings(
            django_extra_settings={
                "BA_API_KEY_REQUEST_HEADER": env(
                    "BA_API_KEY_REQUEST_HEADER", default="HTTP_API_KEY"
                ),
                "BA_API_KEY_ENCRYPTION_KEY": env("BA_API_KEY_ENCRYPTION_KEY", default=None),
            },
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": "If active, it will load the current_profile from the used api key."
                }
            ],
        )
