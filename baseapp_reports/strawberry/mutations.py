import strawberry
import swapper
from django.apps import apps
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.strawberry import (
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
)
from baseapp_core.strawberry.connections import Edge, offset_to_cursor

from ..permissions import ADD_REPORT_PERMISSION
from .interfaces import ReportsInterface
from .types import ReportLazyType

Report = swapper.load_model("baseapp_reports", "Report")


@strawberry.input(name="ReportCreateInput")
class ReportCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    report_type_id: strawberry.ID
    report_subject: str | None = UNSET


@strawberry.type(name="ReportCreatePayload")
class ReportCreatePayload(RelayMutationPayload):
    report: Edge[ReportLazyType] | None = None
    target: ReportsInterface | None = None


@strawberry.type
class ReportsMutations:
    @relay_mutation(login_required=True)
    def report_create(self, info: Info, input: ReportCreateInput) -> ReportCreatePayload | None:
        user = info.context.user
        target = get_obj_from_relay_id(info, input.target_object_id)
        report_type = get_obj_from_relay_id(info, input.report_type_id)
        report_subject = None if input.report_subject is UNSET else input.report_subject

        if not user.has_perm(ADD_REPORT_PERMISSION, target):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        if apps.is_installed("baseapp_profiles"):
            current_profile = getattr(user, "current_profile", None)
            is_self_report = bool(current_profile and current_profile.relay_id == target.relay_id)
        else:
            is_self_report = getattr(target, "user_id", None) == user.id or (
                getattr(target, "pk", None) == user.id
            )

        if is_self_report:
            raise GraphQLError(
                str(_("You cannot report yourself")),
                extensions={"code": "invalid_action"},
            )

        report = Report.objects.create(
            user=user,
            target_document=DocumentId.get_or_create_for_object(target),
            report_type=report_type,
            report_subject=report_subject,
        )

        target.refresh_from_db()

        return ReportCreatePayload(
            report=Edge(node=report, cursor=offset_to_cursor(0)), target=target
        )
