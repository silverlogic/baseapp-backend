from typing import TYPE_CHECKING, Any

import graphene
import swapper
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

from ..services import get_impersonation

if TYPE_CHECKING:
    from django.db.models import QuerySet

ImpersonationSession = swapper.load_model("baseapp_impersonation", "ImpersonationSession")

VIEW_PERMISSION = (
    f"{ImpersonationSession._meta.app_label}.view_{ImpersonationSession._meta.model_name}"
)

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

    def resolve_end_reason(self, info: graphene.ResolveInfo) -> str | None:
        return self.end_reason or None

    def resolve_is_active(self, info: graphene.ResolveInfo) -> bool:
        return self.is_active

    @classmethod
    def get_queryset(
        cls, queryset: "QuerySet[ImpersonationSession]", info: graphene.ResolveInfo
    ) -> "QuerySet[ImpersonationSession]":
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
    def get_node(cls, info: graphene.ResolveInfo, id: Any) -> "ImpersonationSession | None":
        """The session, only when `get_queryset` lets the viewer see it."""
        return cls.get_queryset(ImpersonationSession.objects.all(), info).filter(pk=id).first()


class ImpersonationSessionObjectType(BaseImpersonationSessionObjectType, DjangoObjectType):
    class Meta(BaseImpersonationSessionObjectType.Meta):
        pass
