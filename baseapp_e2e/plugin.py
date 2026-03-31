from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class E2EPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_e2e"

    @property
    def package_name(self) -> str:
        return "baseapp_e2e"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            django_extra_settings={
                # If needed, override this E2E setting and define the SCRIPTS_PACKAGE to enable E2E tests.
                "E2E": {
                    "ENABLED": False,
                    # Example of script:
                    # "SCRIPTS_PACKAGE": "testproject.e2e.scripts",
                },
            },
            required_packages=[],
            optional_packages=[],
        )
