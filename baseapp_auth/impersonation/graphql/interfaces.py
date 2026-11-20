import graphene
from django.utils.translation import gettext_lazy as _

from ..services import get_impersonation


def get_impersonation_interface() -> type[graphene.Interface]:
    from .object_types import ImpersonationSessionObjectType

    class ImpersonationInterface(graphene.Interface):
        impersonation = graphene.Field(
            ImpersonationSessionObjectType,
            description=_(
                "The impersonation session of the current request, when this user is its "
                "target. Null otherwise, and on every other user."
            ),
        )

        def resolve_impersonation(self, info) -> object | None:
            session = get_impersonation(info.context)
            if session is None or session.target_id != self.pk:
                return None
            if getattr(info.context.user, "pk", None) != self.pk:
                return None
            return session

    return ImpersonationInterface
