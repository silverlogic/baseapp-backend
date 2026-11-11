from typing import TYPE_CHECKING, Any

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.urls import URLResolver


# The default prefix of card hold idempotency keys; holds.key_prefix() falls back to it.
DEFAULT_CARD_HOLD_KEY_PREFIX = "baseapp"


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
                # Card holds (opt-in through BASEAPP_PAYMENTS_CARDHOLD_MODEL). The models a
                # hold can back, as {"app_label.Model": "dotted.path.to.Adapter"}.
                "BASEAPP_PAYMENTS_CARD_HOLD_TARGETS": {},
                # Prefix of every Stripe idempotency key card holds send. Give each
                # project sharing a Stripe account its own.
                "BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX": DEFAULT_CARD_HOLD_KEY_PREFIX,
            },
            # Staff decisions on a failed deferred hold (cardHoldKeep / cardHoldCancel).
            # The class is empty without a card hold model.
            graphql_mutations=[
                "baseapp_payments.graphql.mutations.CardHoldMutations",
            ],
            constance_config={
                # Read only for targets whose adapter uses holds; listed for every
                # project, like the beat entry below.
                "CARD_HOLDS_BUFFER_PERCENT": (
                    10,
                    "Card holds: percent added on top of the value, for targets whose"
                    " adapter declares hold_amount_mode = value_plus_buffer.",
                    int,
                ),
                "CARD_HOLDS_WINDOW_DAYS": (
                    4,
                    "Card holds: days before a target's date to place its deferred hold"
                    " (1-4: a Visa hold placed without the customer lasts 4 days 18 hours).",
                    int,
                ),
                "CARD_HOLDS_DEFERRAL_ENABLED": (
                    False,
                    "Card holds: place holds for far-off targets later, without the customer.",
                    bool,
                ),
            },
            # Registered for every project: these settings are built while the project's
            # settings module is still loading, before BASEAPP_PAYMENTS_CARDHOLD_MODEL can
            # be read. Without a card hold model the sweep returns before any query.
            celery_beat_schedules={
                "baseapp_payments_card_holds_sweep": {
                    "task": "baseapp_payments.tasks.sweep_card_holds",
                    "schedule": 15 * 60,
                    # As long as the interval, so a backed-up beat never runs duplicates.
                    "options": {"expires": 15 * 60},
                },
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
