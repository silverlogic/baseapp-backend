from typing import TYPE_CHECKING

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings

if TYPE_CHECKING:
    from django.urls import URLResolver


class PaymentsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_payments"

    @property
    def package_name(self) -> str:
        return "baseapp_payments"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            v1_urlpatterns=self.v1_urlpatterns,
            required_packages=[],
            optional_packages=[],
        )

    @staticmethod
    def v1_urlpatterns(include, path, re_path) -> "list[URLResolver]":
        from baseapp_payments.router import payments_router

        return [
            re_path(r"payments/", include(payments_router.urls)),
        ]
