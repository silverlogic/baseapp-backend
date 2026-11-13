from importlib.util import find_spec
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig, GraphQLContributor

if TYPE_CHECKING:
    from baseapp_core.plugins import GraphQLSharedInterfaceRegistry


class PackageConfig(BaseAppConfig, GraphQLContributor):
    default = True
    name = "baseapp_payments"
    label = "baseapp_payments"
    verbose_name = _("BaseApp Payments")
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        super().ready()
        from .models import card_holds_enabled

        if card_holds_enabled():
            from .signals import connect_target_receivers

            connect_target_receivers()

    def register_graphql_shared_interfaces(
        self, registry: "GraphQLSharedInterfaceRegistry"
    ) -> None:
        from .models import card_holds_enabled

        # The REST surface needs neither: only a project with card holds and the graphql
        # extra gets the interface.
        if not card_holds_enabled() or find_spec("graphene_django") is None:
            return
        from .graphql.interfaces import get_card_holds_interface

        registry.register("CardHoldsInterface", get_card_holds_interface)
