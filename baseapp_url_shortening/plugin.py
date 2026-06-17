from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class UrlShorteningPlugin(BaseAppPlugin):
    """
    The Url Shortening plugin is used to shorten urls.
    """

    @property
    def name(self) -> str:
        return "baseapp_url_shortening"

    @property
    def package_name(self) -> str:
        return "baseapp_url_shortening"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            django_extra_settings={},
            # Plugin deps
            required_packages=[],
            optional_packages=[],
            # URLs
            v1_urlpatterns=self.v1_urlpatterns,
        )

    def v1_urlpatterns(self, include, path, re_path):
        return [
            path(r"", include("baseapp_url_shortening.urls")),
        ]
