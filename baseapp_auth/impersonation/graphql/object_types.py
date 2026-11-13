from typing import TYPE_CHECKING

import graphene
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

from ..models import ImpersonationSession
from ..services import get_impersonation

if TYPE_CHECKING:
    from django.db.models import QuerySet


VIEW_PERMISSION = f"{ImpersonationSession._meta.app_label}.view_impersonationsession"

ImpersonationEndReason = graphene.Enum.from_enum(
    ImpersonationSession.EndReason, name="ImpersonationEndReason"
)


class BaseImpersonationSessionObjectType:
    end_reason = graphene.Field(
        ImpersonationEndReason, description=_("Why the session ended. Null while it runs.")
    )
    is_active = graphene.Boolean(
        required=True, description=_("Whether the session is still running.")
    )

    class Meta:
        model = ImpersonationSession
        interfaces = (RelayNode,)
        fields = (
            "id",
            "impersonator",
            "target",
            "reason",
            "read_only",
            "started_at",
            "expires_at",
            "ended_at",
            "end_reason",
        )

    def resolve_end_reason(self, info) -> str | None:
        return self.end_reason or None

    def resolve_is_active(self, info) -> bool:
        return self.is_active

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet[ImpersonationSession]":
        """Staff with the view permission see every session; others see the ones they
        started and the one their request belongs to."""
        user = info.context.user
        if not user.is_authenticated:
            return queryset.none()
        if user.has_perm(VIEW_PERMISSION):
            return queryset
        visible = Q(impersonator_id=user.pk)
        if session := get_impersonation(info.context):
            visible |= Q(pk=session.pk)
        return queryset.filter(visible)

    @classmethod
    def get_node(cls, info, id) -> "ImpersonationSession | None":
        node = super().get_node(info, id)
        if (
            node is None
            or not cls.get_queryset(ImpersonationSession.objects.filter(pk=node.pk), info).exists()
        ):
            return None
        return node


class ImpersonationSessionObjectType(BaseImpersonationSessionObjectType, DjangoObjectType):
    class Meta(BaseImpersonationSessionObjectType.Meta):
        pass
