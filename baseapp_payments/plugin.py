from typing import TYPE_CHECKING, Any

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings

if TYPE_CHECKING:
    from collections.abc import Callable

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
            AUTHENTICATION_BACKENDS={
                "baseapp_payments": [
                    "baseapp_payments.permissions.PaymentsPermissionsBackend",
                ],
            },
            django_extra_settings={
                # Dotted path to `check(entity, user_obj) -> bool`, deciding who may bill
                # an entity. The default handles a `baseapp_profiles` Profile and the user
                # model; any other STRIPE_CUSTOMER_ENTITY_MODEL must supply its own, since
                # the block cannot know what ownership means for it.
                "BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK": (
                    "baseapp_payments.permissions.default_entity_owner_check"
                ),
            },
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": (
                        "If enabled, the default entity-owner check treats a Profile as"
                        " billable by its owner, the user whose own profile it is, or an"
                        " active ADMIN member."
                    )
                },
            ],
        )

    @staticmethod
    def v1_urlpatterns(
        include: "Callable[..., Any]",
        path: "Callable[..., Any]",
        re_path: "Callable[..., Any]",
    ) -> "list[URLResolver]":
        from baseapp_payments.router import payments_router

        return [
            re_path(r"payments/", include(payments_router.urls)),
        ]
